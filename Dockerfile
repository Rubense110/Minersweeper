# Usa una imagen base con Python
FROM python:3.12-slim

# Establece el directorio de trabajo
WORKDIR /app

# Copia los requisitos
COPY requirements.txt .

# Instala dependencias del sistema necesarias (graphviz + pg_config para psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    graphviz \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del código
COPY . .

# Expone el puerto
EXPOSE 8000
