# Use official ubuntu runtime as a parent image
FROM python:3.10-slim as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV ACCEPT_EULA=Y
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-dev \
    python3-venv \
    tesseract-ocr \
    libtesseract-dev \
    bash \
    curl \
    gnupg \
    apt-transport-https \
    ca-certificates \
    build-essential \
    unixodbc \
    unixodbc-dev \
    freetds-dev && \
    curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
    curl https://packages.microsoft.com/config/ubuntu/22.04/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
    msodbcsql18 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
WORKDIR /app
COPY . .

# Copy the configuration file as is
COPY custom_edi.config /app/config_for_edi.config

RUN chmod +x entrypoint.sh

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --upgrade pip setuptools wheel
 
# Define the command to run the application using Gunicorn
CMD ["sh", "/app/entrypoint.sh"]

