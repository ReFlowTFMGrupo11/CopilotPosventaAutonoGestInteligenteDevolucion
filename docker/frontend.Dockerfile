# Imagen del frontend Streamlit (frontend/Chat.py, puerto 8501).
#
# Build de contexto = raíz del repo:
#   docker build -f docker/frontend.Dockerfile -t reflow-frontend:latest .
#
# Ver docker/api.Dockerfile para el porqué del patrón multi-stage.
FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /install /usr/local

COPY frontend/ frontend/

ENV PYTHONUNBUFFERED=1

# Evita que Streamlit pida un email por stdin en el primer arranque (mismo
# problema que resuelve start_all_mac.sh escribiendo ~/.streamlit/credentials.toml
# a mano) — aquí se hace vía env var porque no hay terminal interactiva en
# un contenedor/task de Fargate.
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Necesario para que frontend/lib/api.py llame al backend correcto: dentro
# de un contenedor, "http://localhost:8000" (el default de api.py) NO es el
# backend, es el propio contenedor del frontend. En ECS, sobreescribir esta
# env var en la task definition con la URL del Service Connect del backend
# o la del ALB (ver docs/deployment_aws_ecs_fargate.md). El valor de aquí
# solo sirve como placeholder explícito para que "docker run" sin -e falle
# de forma obvia (connection refused) en vez de conectar en silencio a sí
# mismo.
ENV API_BASE_URL=http://backend:8000

EXPOSE 8501

# /_stcore/health es el healthcheck interno que trae Streamlit de fábrica
# (no hay que definir un endpoint propio, a diferencia de la API).
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)"

CMD ["streamlit", "run", "frontend/Chat.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
