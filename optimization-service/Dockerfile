FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    graphviz \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY optimization-service /app/optimization-service

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/optimization-service

WORKDIR /app/optimization-service

ENV OPTIMIZATION_HOST=0.0.0.0
ENV OPTIMIZATION_PORT=8080

EXPOSE 8080

CMD ["python", "api.py"]
