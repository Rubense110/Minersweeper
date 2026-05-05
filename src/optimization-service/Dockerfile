FROM python:3.12-slim

WORKDIR /app

COPY src/optimization-service/requirements.txt /app/src/optimization-service/requirements.txt

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    graphviz \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r /app/src/optimization-service/requirements.txt

COPY src/optimization-service /app/src/optimization-service

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src/optimization-service/src

WORKDIR /app/src/optimization-service

ENV OPTIMIZATION_HOST=0.0.0.0
ENV OPTIMIZATION_PORT=8080

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--worker-class", "gthread", "--threads", "8", "--timeout", "600", "--graceful-timeout", "30", "api:app"]
