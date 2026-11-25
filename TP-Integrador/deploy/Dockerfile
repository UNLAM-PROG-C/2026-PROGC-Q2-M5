# Servidor online de Futbol de Cabeza: sólo necesita la librería websockets
# (la simulación y el servidor no usan pygame ni numpy; ver
# tests/check_sim_imports.py). Se construye desde la raíz del repositorio:
#   docker build -f deploy/Dockerfile -t fdc-server .
FROM python:3.12-slim

# Sin buffers: los registros salen en orden en `docker compose logs`.
# Sin .pyc: la imagen queda igual en cada arranque.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Primero las dependencias: la capa se reusa si no cambian.
COPY deploy/requirements-server.txt ./requirements-server.txt
RUN pip install --no-cache-dir -r requirements-server.txt

# Server code.
COPY deploy/server.py ./server.py
COPY fdc ./fdc

# Usuario sin privilegios y su carpeta de registros (logs/server.log).
RUN useradd --create-home --uid 10001 fdc \
    && mkdir -p /app/logs \
    && chown -R fdc:fdc /app
USER fdc

# El puerto DENTRO del contenedor no se cambia; el del host lo elige
# FDC_HOST_PORT en deploy/.env.
EXPOSE 8765

# /status.json es la vista pública del panel: sirve de prueba de vida.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8765/status.json', timeout=4)"

CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "8765"]
