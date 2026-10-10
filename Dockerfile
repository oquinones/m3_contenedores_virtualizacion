# TODO: Crear Dockerfile para la aplicación FastAPI
# FROM python:3.14.8-slim
FROM python:3.14.8-slim

# TODO: Crear usuario no-root para seguridad
# RUN useradd -m -u 1000 appuser
RUN useradd -m -u 1000 appuser

# TODO: Establecer directorio de trabajo
# WORKDIR /app
WORKDIR /app

# TODO: Instalar dependencias del sistema necesarias (gcc, postgresql-client)
# RUN apt-get update && apt-get install -y ...
RUN apt-get update && apt-get install -y gcc postgresql-client
# TODO: Copiar requirements.txt e instalar dependencias Python
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# TODO: Copiar código de la aplicación
# COPY . .
COPY api/ ./api
# TODO: Cambiar ownership y usuario
# RUN chown -R appuser:appuser /app
# USER appuser
RUN chown -R appuser:appuser /app
USER appuser

# TODO: Exponer puerto 8080
# EXPOSE 8080
EXPOSE 8080

# TODO: Ejecutar aplicación con uvicorn
# CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
