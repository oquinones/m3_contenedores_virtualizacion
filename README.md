# Task Management API

> API REST para la gestión de tareas desarrollada con **FastAPI**. El proyecto aplica los principios de programación orientada a objetos (encapsulamiento, abstracción) y sigue las convenciones de estilo **PEP 8**.

---

## Caracteristicas

- Crear una nueva tarea.
- Listar todas las tareas.
- Obtener una tarea por su `id`.
- Marcar una tarea como completada.
- Eliminar una tarea por su `id`.
- Listar las tareas caducadas (fecha de vencimiento anterior a hoy y no completadas).
- Persistencia en base de datos **PostgreSQL** mediante **SQLAlchemy** y el driver **psycopg 3**.
- Conexión a la base de datos configurable mediante la variable de entorno `DATABASE_URL`.
- Lógica de negocio encapsulada en una clase de servicio (`TaskManager`).
- Gestión de transacciones: si falla un `commit`, se hace `rollback` y se registra el error.
- Gestión de errores con códigos HTTP apropiados (`200`, `201`, `204`, `400`, `404`, `500`).
- Logging de las operaciones y de los errores.
- Imagen Docker de la aplicación.

## Stack Tecnologico

| Herramienta | Uso |
|-------------|-----|
| Python 3.14 | Lenguaje principal |
| FastAPI | Framework web |
| Pydantic | Validación y serialización de datos |
| SQLAlchemy | ORM para el acceso a PostgreSQL |
| psycopg 3 (`psycopg[binary]`) | Driver de PostgreSQL |
| PostgreSQL | Base de datos (base de datos `task`, tabla `tasks`) |
| Uvicorn | Servidor ASGI |
| Docker | Contenedorización de la aplicación |
| requests | Pruebas de los endpoints |

## Estructura del proyecto
```text
m3_contenedores_virtualizacion/
├── api/
│   ├── __init__.py
│   └── main.py              # Crea la app, configura la BBDD, implementa TaskManager y los manejadores de errores
├── .dockerignore            # Ficheros excluidos de la imagen Docker
├── docker-compose.yml       # Plantilla de Docker Compose (app + PostgreSQL), pendiente de completar
├── Dockerfile               # Imagen Docker de la aplicación
├── requirements.txt         # Dependencias del proyecto (gestionadas con pip)
├── ruff.toml                # Configuración de Ruff (estilo PEP 8)
├── README_BUILD.md          # Guía de despliegue con Docker Compose
└── README.md
```

## Base de datos

La persistencia se realiza en un servidor **PostgreSQL**. El modelo de datos y la lógica de negocio no cambian; lo que cambia es la configuración del acceso a datos en `api/main.py`:

| Aspecto | PostgreSQL |
|---------|--------------------|
| Ubicación de los datos | Servidor PostgreSQL, base de datos `task_db` |
| Configuración | Variable de entorno `DATABASE_URL` (con un valor por defecto) |
| Driver | `psycopg` v3 (`psycopg[binary]` en `requirements.txt`) |
| Motor SQLAlchemy | Pool de conexiones con `pool_pre_ping=True` (comprueba que la conexión sigue viva antes de usarla) |
| Columnas de texto | `VARCHAR(100)` / `VARCHAR(300)` aplicadas por PostgreSQL y alineadas con la validación de Pydantic |
| Ciclo de vida | Se crean las tablas al arrancar (`create_all`) y se libera el pool de conexiones al parar (`engine.dispose()`) |

### Cadena de conexión (`DATABASE_URL`)

```text
postgresql://<usuario>:<contraseña>@<host>:<puerto>/<base_de_datos>
```

- Si la URL empieza por `postgresql://` o `postgres://`, la aplicación la reescribe a `postgresql+psycopg://` para forzar el uso de psycopg 3 (función `_build_database_url`). Así se puede usar el formato estándar que suelen dar Docker o los proveedores cloud.
- Si `DATABASE_URL` no está definida, se usa la URL por defecto `DEFAULT_DATABASE_URL` de `api/main.py`, pensada solo para desarrollo. En cualquier otro entorno conviene definir siempre `DATABASE_URL`.
- Al arrancar, la aplicación crea la tabla `tasks` si no existe (`Base.metadata.create_all`). La base de datos (`task_db`) sí tiene que existir antes.
- La URL de conexión se escribe en el log al arrancar con la contraseña oculta (`***`).

## Modelo de Datos

### Tabla `tasks` (`TaskDB`)

| Columna | Tipo PostgreSQL | Restricciones |
|---------|-----------------|---------------|
| `task_id` | `INTEGER` | Clave primaria, autoincremental, indexada |
| `task_title` | `VARCHAR(100)` | `NOT NULL` |
| `task_content` | `VARCHAR(300)` | `NOT NULL` |
| `creation_date` | `TIMESTAMP` | Por defecto, fecha y hora actual |
| `update_date` | `TIMESTAMP` | Por defecto, fecha y hora actual; se actualiza al modificar |
| `deadline` | `DATE` | `NOT NULL` |
| `task_completed` | `BOOLEAN` | Por defecto `false` |
| `assigned_user` | `VARCHAR(100)` | Admite `NULL` |

### Registro de tareas (`TaskResponse`)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `task_id` | `int` | Identificador único (autogenerado) |
| `task_title` | `str` | Título de la tarea |
| `task_content` | `str` | Descripción de la tarea |
| `creation_date` | `datetime` (ISO 8601) | Fecha y hora de creación (autogenerada) |
| `update_date` | `datetime` (ISO 8601) | Fecha y hora de actualizacion (autogenerada) |
| `deadline` | `date` (`YYYY-MM-DD`) | Fecha de vencimiento |
| `task_completed` | `bool` | Indica si la tarea está completada (por defecto `false`) |
| `assigned_user` | `str` | Nombre del usuario que tiene asignada la tarea (por defecto `None`) |


### Creación de tarea (`TaskCreate`)

| Campo | Tipo | Obligatorio | Restricciones |
|-------|------|:-----------:|---------------|
| `task_title` | `str` | Sí | Entre 1 y 100 caracteres; no vacío (tampoco solo espacios); se normalizan los espacios |
| `task_content` | `str` | Sí | Entre 1 y 300 caracteres; no vacío (tampoco solo espacios); se normalizan los espacios |
| `deadline` | `date` | Sí | Formato `YYYY-MM-DD`; `deadline` >= `creation_date` y  `deadline` <= (`creation_date` + 15 dias) |
| `assigned_user` | `str` | No | Entre 4 y 100 caracteres (por defecto `None`); se normalizan los espacios |

## Endpoints

| Método | Ruta | Descripción | Éxito | Errores |
|--------|------|-------------|:-----:|:-------:|
| `GET` | `/` | Información de la API | 200 | — |
| `POST` | `/tasks/` | Crear una nueva tarea | 201 | 400 |
| `GET` | `/tasks/` | Listar todas las tareas | 200 | — |
| `GET` | `/tasks/{task_id}` | Obtener una tarea por su id | 200 | 400, 404 |
| `PUT` | `/tasks/{task_id}/completar` | Marcar una tarea como completada | 200 | 400, 404 |
| `DELETE` | `/tasks/{task_id}` | Eliminar una tarea por su id | 204 | 400, 404 |
| `GET` | `/tasks/caducadas` | Listar las tareas caducadas | 200 | — |

Cualquier endpoint puede devolver `500` si se produce un error no controlado (por ejemplo, si no se puede conectar con PostgreSQL).

---

## Arquitectura y diseño POO

La aplicación separa responsabilidades en capas:

1. **Modelos Pydantic** (`TaskCreate`, `TaskUpdate`, `TaskResponse`): definen el contrato de entrada y salida de la API y validan los datos recibidos.
2. **Modelo de persistencia** (`TaskDB`, tabla `tasks` en SQLAlchemy): representa la entidad tarea en PostgreSQL.
3. **Clase de servicio `TaskManager`**: encapsula toda la lógica de negocio relacionada con las tareas:
   - **transformación del contenido**: `_clean_text` elimina los espacios al inicio y al final y reduce los espacios repetidos a uno (`"  Hola   mundo "` → `"Hola mundo"`),
   - **validaciones**: `task_title` y `task_content` no pueden quedar vacíos tras la limpieza; la fecha del `deadline` no puede ser menor que la fecha de creación `creation_date` y mayor a 15 dias despues de la fecha de creación `creation_date`.
   - **comprobación de fechas**: detección de tareas caducadas,
   - **acceso a la base de datos** mediante una sesión privada (`self.__db`),
   - **transacciones**: `_commit` confirma los cambios y, si PostgreSQL devuelve un error (`SQLAlchemyError`), hace `rollback`, lo registra en el log y relanza la excepción.

   | Método público | Descripción |
   |----------------|-------------|
   | `create_task(data)` | Limpia, valida y guarda una tarea |
   | `list_tasks()` | Todas las tareas, ordenadas por `deadline` y `task_id` |
   | `get_task(task_id)` | Devuelve la tarea o lanza `TaskNotFoundError` |
   | `mark_completed(task_id)` | Marca la tarea como completada (idempotente) |
   | `delete_task(task_id)` | Elimina la tarea o lanza `TaskNotFoundError` |
   | `get_expired_tasks()` | Tareas no completadas con `deadline` anterior a hoy, ordenadas por fecha |

   Los endpoints no acceden directamente a la base de datos: delegan en `TaskManager`, que oculta los detalles de implementación (**encapsulamiento**) y expone una interfaz sencilla de operaciones (**abstracción**). Gracias a esta separación, el cambio de SQLite a PostgreSQL solo ha afectado a la configuración de la base de datos, no a los endpoints ni a la lógica de negocio. Los errores de negocio se lanzan como excepciones de dominio (`TaskNotFoundError`, `InvalidTaskError`) que los manejadores de errores de `api/main.py` traducen a `404` y `400`. Los datos de entrada que no superan la validación de Pydantic también devuelven `400` (en lugar del `422` por defecto de FastAPI), y un middleware captura cualquier otra excepción, la registra con su traza y devuelve `500`.
4. **Endpoints FastAPI**: reciben la petición, invocan al servicio y traducen el resultado (o la excepción) al código HTTP correspondiente. Cada petición abre su propia sesión de base de datos (`get_db`) y la cierra al terminar.

## Instalación

### 1. Disponer de un servidor PostgreSQL

La aplicación necesita un servidor PostgreSQL accesible con una base de datos `task_db` creada. La forma más sencilla es levantarlo con Docker:

```bash
docker run -d --name task-db \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=<contraseña> \
  -e POSTGRES_DB=task_db \
  -v task-db-data:/var/lib/postgresql/data \
  -p 5432:5432 \
  postgres:16-alpine
```

Los datos se guardan en el volumen `task-db-data`, por lo que se conservan aunque se elimine el contenedor.

### 2. Crear entorno virtual

```bash
# Windows
python -m venv env
env\Scripts\activate

# Linux/Mac
python -m venv env
source env/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar la conexión y ejecutar la aplicación

Desde la raíz del proyecto:

```bash
# Windows (PowerShell)
$env:DATABASE_URL = "postgresql://postgres:<contraseña>@localhost:5432/task_db"

# Linux/Mac
export DATABASE_URL="postgresql://postgres:<contraseña>@localhost:5432/task_db"

# Opción 1: Comando moderno de FastAPI (recomendado)
fastapi dev api/main.py

# Opción 2: Uvicorn tradicional
uvicorn api.main:app --reload
```

La API estará disponible en `http://localhost:8080`. Al arrancar, el log muestra la línea `Connected to database at ...` con la URL usada (contraseña oculta).

### 4.1. Ejecutar con Docker (alternativa)

La aplicación y PostgreSQL se ejecutan en contenedores conectados a una misma red, de modo que la aplicación accede a la base de datos por el nombre del contenedor (`task-db`):

```bash
# Crear la red y arrancar PostgreSQL en ella
docker network create task-net
docker run -d --name task-db --network task-net \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=<contraseña> \
  -e POSTGRES_DB=task_db \
  -v task-db-data:/var/lib/postgresql/data \
  postgres:16-alpine

# Construir la imagen de la aplicación (desde la raíz del proyecto)
docker build -t task-management-api .

# Arrancar la aplicación indicando la conexión con DATABASE_URL
docker run -d --name task-api --network task-net -p 8080:8080 \
  -e DATABASE_URL=postgresql://postgres:<contraseña>@task-db:5432/task \
  task-management-api
```

La API estará disponible en `http://localhost:8080`. Para detener y eliminar los contenedores (los datos se conservan en el volumen `task-db-data`):

```bash
docker rm -f task-api task-db
```

> La imagen se basa en `python:3.14.8-slim`, incluye `postgresql-client`, se ejecuta con un usuario sin privilegios (`appuser`), expone el puerto `8080` y solo copia la carpeta `api/` (ver `Dockerfile` y `.dockerignore`).

La plantilla `misc/docker-compose.yml` y la guía `README_BUILD.md` describen el despliegue de ambos servicios con Docker Compose (`docker compose up --build`).

## 5. Uso de los endpoints

### `GET /` — Información de la API

Respuesta `200`:

```json
{"message": "Task Management API"}
```

### `POST /tasks/` — Crear una nueva tarea

Cuerpo (`TaskCreate`):

```json
{
  "task_title": "  Preparar   informe ",
  "task_content": "Resumen mensual",
  "deadline": "2026-10-17",
  "assigned_user": "ana.garcia"
}
```

Respuesta `201` (`TaskResponse`), con los textos normalizados:

```json
{
  "task_id": 1,
  "task_title": "Preparar informe",
  "task_content": "Resumen mensual",
  "creation_date": "2026-10-10T19:29:25.204700",
  "update_date": "2026-10-10T19:29:25.204700",
  "deadline": "2026-10-17",
  "task_completed": false,
  "assigned_user": "ana.garcia"
}
```

Errores `400`: campos obligatorios ausentes, `task_title`/`task_content` vacíos (o solo espacios) o demasiado largos, `assigned_user` con menos de 4 caracteres, fecha con formato incorrecto, o `deadline` fuera del rango [hoy, hoy + 15 días].

### `GET /tasks/` — Listar todas las tareas

Respuesta `200` con una lista de `TaskResponse` ordenada por `deadline` (y por `task_id` en caso de empate). Si no hay ninguna, devuelve `[]`.

### `GET /tasks/{task_id}` — Obtener una tarea por su id

Respuesta `200` con la tarea (`TaskResponse`).

- `400`: `task_id` no es un entero mayor que 0 (p. ej. `/tasks/abc` o `/tasks/0`).
- `404`: la tarea no existe.

### `PUT /tasks/{task_id}/completar` — Marcar una tarea como completada

No requiere cuerpo. Respuesta `200` con la tarea y `task_completed: true`. Es idempotente: completar una tarea ya completada devuelve `200` sin modificarla.

- `400`: `task_id` no es un entero mayor que 0.
- `404`: la tarea no existe.

### `DELETE /tasks/{task_id}` — Eliminar una tarea

No requiere cuerpo. Respuesta `204 No Content` (sin cuerpo) si la tarea se ha eliminado. Eliminarla de nuevo devuelve `404`.

- `400`: `task_id` no es un entero mayor que 0.
- `404`: la tarea no existe.

### `GET /tasks/caducadas` — Listar las tareas caducadas

Respuesta `200` con una lista de `TaskResponse`: tareas no completadas cuyo `deadline` es anterior a hoy, ordenadas por `deadline` ascendente. Si no hay ninguna, devuelve `[]`.

### Formato de los errores

- Errores de validación de entrada: `{"detail": [ ...lista de errores de Pydantic... ]}`
- Errores de negocio: `{"detail": "<mensaje>"}`, p. ej. `{"detail": "The task with id 990000 does not exist"}`
- Errores no controlados (p. ej. base de datos no disponible): `{"detail": "Internal server error"}` con código `500`.

## Documentación interactiva

Una vez ejecutando la aplicación, puedes acceder a (usa el puerto `8080` si la ejecutas con Docker):
- Swagger UI: `http://localhost:8080/docs`
- ReDoc: `http://localhost:8080/redoc`
