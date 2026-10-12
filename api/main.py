"""
Main Script for the Task Management API

This script implements a RESTful API for task management using FastAPI.

It provides endpoints for creating, retrieving, updating, and listing tasks,
as well as for handling application-specific errors.
"""

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
import logging
from pathlib import Path as FilePath
from typing import Annotated

from fastapi import Depends, FastAPI, Path, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import (
    URL,
    Boolean,
    Date,
    DateTime,
    Identity,
    Integer,
    String,
    create_engine,
    select,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

BASE_DIR = FilePath(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"


# Mark: --- Settings ---
class Settings(BaseSettings):
    """
    The application settings loaded from environment variables and the .env file.
    If they are not defined, the default values listed below are used.
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

    app_title: str = "Task Management API"
    app_version: str = "1.0.1"
    app_description: str = "API for Task Management"
    postgres_user: str = "postgres"
    postgres_password: str = ""
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "task_db"
    database_url: str | None = None
    task_id_min: int = 10_000_000
    task_id_max: int = 99_999_999

    @property
    def sqlalchemy_url(self) -> str | URL:
        """
        Returns DATABASE_URL if it is defined (e.g. in Docker Compose);
        otherwise builds it from the POSTGRES_* settings.
        """
        if self.database_url:
            return _build_database_url(self.database_url)
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


def _build_database_url(url: str) -> str:
    """Forces the psycopg (v3) driver for plain 'postgresql://' URLs."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    return url


settings = Settings()

# Mark:--- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Mark: --- DB setup ---
engine = create_engine(settings.sqlalchemy_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


class TaskDB(Base):
    """Database schema for the tasks table in the BBDD."""

    __tablename__ = "tasks"

    # PostgreSQL generates 8-digit ids within [TASK_ID_MIN, TASK_ID_MAX]
    task_id: Mapped[int] = mapped_column(
        Integer,
        Identity(
            start=settings.task_id_min,
            minvalue=settings.task_id_min,
            maxvalue=settings.task_id_max,
        ),
        primary_key=True,
        index=True,
    )
    task_title: Mapped[str] = mapped_column(String(100), nullable=False)
    task_content: Mapped[str] = mapped_column(String(300), nullable=False)
    creation_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    update_date: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
    )
    deadline: Mapped[date] = mapped_column(Date, nullable=False)
    task_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_user: Mapped[str | None] = mapped_column(String(100), nullable=True)


# Mark: --- FastAPI setup ---
@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Creates the database tables on startup and releases the pool on shutdown."""
    Base.metadata.create_all(bind=engine)
    logger.info("Connected to database at %s", engine.url.render_as_string())
    yield
    engine.dispose()


app = FastAPI(
    title=settings.app_title,
    description=settings.app_description,
    version=settings.app_version,
    lifespan=lifespan,
)


# Mark: --- Pydantic model ---
class TaskCreate(BaseModel):
    """Input data model for creating a task."""

    task_title: str = Field(..., min_length=1, description="Task title", max_length=100)
    task_content: str = Field(
        ..., min_length=1, description="Task content", max_length=300
    )
    deadline: date = Field(..., description="Due date")
    assigned_user: str | None = Field(
        default=None,
        min_length=4,
        description="User assigned to the task",
        max_length=100,
    )


class TaskUpdate(BaseModel):
    """Input data model for updating a task."""

    task_completed: bool = Field(description="Task completion status")
    update_date: datetime = Field(
        default_factory=datetime.now, description="Update date"
    )


class TaskResponse(BaseModel):
    """Output data model for task responses."""

    model_config = ConfigDict(from_attributes=True)

    task_id: int = Field(
        ge=settings.task_id_min,
        le=settings.task_id_max,
        description="8-digit task identifier",
    )
    task_title: str
    task_content: str
    creation_date: datetime
    update_date: datetime
    deadline: date
    task_completed: bool
    assigned_user: str | None = None


# Mark: --- Domain exceptions ---
class TaskNotFoundError(Exception):
    """The requested task does not exist."""

    def __init__(self, task_id: int) -> None:
        super().__init__(f"The task with id {task_id} does not exist")
        self.task_id = task_id


class InvalidTaskError(Exception):
    """The task data does not comply with the business rules."""


# Mark: --- Task Manager Service ---
class TaskManager:
    """Encapsulates the business logic and data access for tasks."""

    MAX_DEADLINE_DAYS = 15

    def __init__(self, db: Session) -> None:
        self.__db = db

    # Mark: --- Local methods ---
    @staticmethod
    def _clean_text(text: str) -> str:
        """Remove leading and trailing spaces and reduce repetitions to one."""
        return " ".join(text.split())

    def _commit(self, operation: str) -> None:
        """Commits the transaction; on failure rolls back, logs and re-raises."""
        try:
            self.__db.commit()
        except SQLAlchemyError:
            self.__db.rollback()
            logger.exception("Database error during '%s', rolled back", operation)
            raise

    def _validate_deadline(self, deadline: date, creation_date: date) -> None:
        """Check that the deadline is a date between the creation date and +15 days."""

        if not isinstance(deadline, date) or isinstance(deadline, datetime):
            raise InvalidTaskError("The deadline must be a date (YYYY-MM-DD)")

        if deadline < creation_date:
            raise InvalidTaskError(
                "The deadline cannot be earlier than the creation date"
            )
        max_deadline = creation_date + timedelta(days=self.MAX_DEADLINE_DAYS)

        if deadline > max_deadline:
            raise InvalidTaskError(
                f"The deadline cannot exceed {self.MAX_DEADLINE_DAYS} days "
                "from the creation date"
            )

    # Mark: --- Public methods ---
    def create_task(self, data: TaskCreate) -> TaskDB:
        """Cleans, validates and saves a task."""
        title = self._clean_text(data.task_title)
        content = self._clean_text(data.task_content)
        if not title:
            raise InvalidTaskError("The task title cannot be empty")
        if not content:
            raise InvalidTaskError("The task content cannot be empty")

        assigned_user = None
        if data.assigned_user is not None:
            assigned_user = self._clean_text(data.assigned_user) or None

        now = datetime.now()
        self._validate_deadline(data.deadline, now.date())

        task = TaskDB(
            task_title=title,
            task_content=content,
            creation_date=now,
            update_date=now,
            deadline=data.deadline,
            task_completed=False,
            assigned_user=assigned_user,
        )
        self.__db.add(task)
        self._commit("create_task")
        self.__db.refresh(task)
        logger.info("Task %s created (deadline=%s)", task.task_id, task.deadline)
        return task

    def get_task(self, task_id: int) -> TaskDB:
        """Returns the task or throws a TaskNotFoundError."""
        task = self.__db.get(TaskDB, task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        logger.info("Task %s retrieved (deadline=%s)", task_id, task.deadline)
        return task

    def mark_completed(self, task_id: int) -> TaskDB:
        """Marks the task as completed."""
        task = self.get_task(task_id)
        if not task.task_completed:
            now = datetime.now()
            task.task_completed = True
            task.update_date = now
            self._commit("mark_completed")
            self.__db.refresh(task)
            logger.info("Task %s marked as completed", task_id)
        return task

    def delete_task(self, task_id: int) -> None:
        """Deletes the task or raises a TaskNotFoundError."""
        task = self.get_task(task_id)
        self.__db.delete(task)
        self._commit("delete_task")
        logger.info("Task %s deleted", task_id)

    def list_tasks(self) -> list[TaskDB]:
        """Returns all tasks ordered by deadline."""
        stmt = select(TaskDB).order_by(TaskDB.deadline, TaskDB.task_id)
        logger.info("Listing all tasks ordered by deadline")
        return list(self.__db.scalars(stmt))

    def get_expired_tasks(self) -> list[TaskDB]:
        """Returns expired tasks."""
        stmt = (
            select(TaskDB)
            .where(TaskDB.task_completed.is_(False), TaskDB.deadline < date.today())
            .order_by(TaskDB.deadline)
        )
        logger.info("Listing expired tasks")
        return list(self.__db.scalars(stmt))


# Mark: --- Dependencies ---
def get_db() -> Iterator[Session]:
    """Opens a database session per request and closes it when done."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_task_manager(db: Annotated[Session, Depends(get_db)]) -> TaskManager:
    """Provides the task service to the endpoints."""
    return TaskManager(db)


TaskManagerDep = Annotated[TaskManager, Depends(get_task_manager)]
TaskIdPath = Annotated[
    int,
    Path(
        ge=settings.task_id_min,
        le=settings.task_id_max,
        description="8-digit id of the task",
    ),
]


# Mark: --- Error handlers ---
@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Logs the validation errors and returns 422 when the input data is invalid."""
    errors = jsonable_encoder(exc.errors())
    logger.warning(
        "Validation error on %s %s: %s", request.method, request.url.path, errors
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": errors},
    )


@app.exception_handler(InvalidTaskError)
async def invalid_task_handler(request: Request, exc: InvalidTaskError) -> JSONResponse:
    """Returns 422 when the task data violates a business rule."""
    logger.warning(
        "Business rule violated on %s %s: %s", request.method, request.url.path, exc
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": str(exc)},
    )


@app.exception_handler(TaskNotFoundError)
async def task_not_found_handler(
    request: Request, exc: TaskNotFoundError
) -> JSONResponse:
    """Returns 404 when the task is not found."""
    logger.warning(
        "Task not found on %s %s (task_id=%s)",
        request.method,
        request.url.path,
        exc.task_id,
    )
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)}
    )


@app.middleware("http")
async def unhandled_exception_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Logs any unhandled exception with its traceback and returns 500."""
    try:
        return await call_next(request)
    except Exception:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )


# Mark: --- Endpoints implementation ---
@app.post("/tasks/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def post_create_task(task: TaskCreate, manager: TaskManagerDep) -> TaskDB:
    """Creates a new task."""
    return manager.create_task(task)


@app.get("/tasks/", response_model=list[TaskResponse])
def list_tasks(manager: TaskManagerDep) -> list[TaskDB]:
    """Returns all tasks ordered by deadline."""
    return manager.list_tasks()


# /tasks/caducadas tiene que declararse antes que /tasks/{task_id};
# si no, FastAPI intentaría interpretar "caducadas" como un id
@app.get("/tasks/caducadas", response_model=list[TaskResponse])
def get_expired_tasks(manager: TaskManagerDep) -> list[TaskDB]:
    """Returns expired tasks."""
    return manager.get_expired_tasks()


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: TaskIdPath, manager: TaskManagerDep) -> TaskDB:
    """Returns a task by its id."""
    return manager.get_task(task_id)


@app.put("/tasks/{task_id}/completar", response_model=TaskResponse)
def mark_completed(task_id: TaskIdPath, manager: TaskManagerDep) -> TaskDB:
    """Marks a task as completed."""
    return manager.mark_completed(task_id)


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: TaskIdPath, manager: TaskManagerDep) -> None:
    """Deletes a task by its id."""
    manager.delete_task(task_id)


@app.get("/")
def root() -> dict[str, str]:
    """Root endpoint of the API."""
    return {"message": "Task Management API"}
