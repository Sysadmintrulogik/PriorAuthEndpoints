# Use official ubuntu runtime as a parent image
FROM python:3.10-slim as builder

ENV DEBIAN_FRONTEND=noninteractive \
    LC_ALL=en_US.UTF-8 \
    LANG=en_US.UTF-8 \
    LANGUAGE=en_US.UTF-8

WORKDIR /app

RUN pip install --upgrade pip setuptools wheel

COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

FROM python:3.10-slim

COPY --from=builder /install /usr/local

WORKDIR /app

COPY . .

CMD ["tail", "-f", "/dev/null"]
