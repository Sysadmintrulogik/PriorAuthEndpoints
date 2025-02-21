# Use official ubuntu runtime as a parent image
FROM python:3.10-slim as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV ACCEPT_EULA=Y
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# Stage 2: Final stage
FROM python:3.10-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY . .
EXPOSE 8000


RUN chmod +x entrypoint.sh

CMD ["sh", "/app/entrypoint.sh"]
