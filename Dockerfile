# Dockerfile for FastAPI application

# Build an image with Python 3.14.8 slim version
FROM python:3.14.8-slim

# Create a non-root user to run the application
RUN useradd -m -u 1000 appuser

# Set the working directory to `/app`
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y gcc postgresql-client

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code to the container
COPY api/ ./api

# Set ownership of the application directory to the non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Expose the port that the application will run on
EXPOSE 8080

# Start the FastAPI application using Uvicorn
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
