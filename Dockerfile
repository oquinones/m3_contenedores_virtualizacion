FROM python:3.14.8-slim

RUN useradd -m -u 1000 appuser

WORKDIR /app

RUN apt-get update && apt-get install -y gcc postgresql-client

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ ./api

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
