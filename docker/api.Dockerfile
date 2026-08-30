# Imagen del backend FastAPI (backend/api/main.py, puerto 8000).
#
# Build de contexto = raíz del repo (no docker/), porque hay que copiar
# requirements.txt y backend/ desde ahí:
#   docker build -f docker/api.Dockerfile -t reflow-api:latest .
#
# Multi-stage: la etapa "builder" instala las dependencias con pip en un
# prefix aislado (/install); la etapa final solo copia ese resultado, sin
# arrastrar la cache de pip ni herramientas de build a la imagen que se
# despliega. Con esto la imagen final pesa menos y tiene menos superficie
# de ataque (sin gcc/build-essential).
FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /install /usr/local

# Solo backend/: el backend nunca importa nada de frontend/, supabase/,
# data/ ni tests/ en tiempo de ejecución (RAG ya vive embebido en Supabase
# pgvector, ver data/rag/ingest_policy_embeddings.py — ese script se corre
# aparte, una vez, no en el contenedor de la API).
COPY backend/ backend/

# Sin esto, el stdout de Python queda bufferizado dentro del contenedor:
# los logger.info(...) de main.py/graph.py/observability.py no llegarían a
# CloudWatch Logs en tiempo real (ver "docker logs -f" o el driver awslogs),
# solo al llenarse el buffer o salir el proceso.
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Usado por Docker en local (docker run --health...) y como referencia para
# el healthCheck del contenedor en la task definition de ECS (ver
# docs/deployment_aws_ecs_fargate.md) — /health está definido en
# backend/api/main.py y no depende de Supabase/OpenAI para responder 200,
# así que solo indica "el proceso está vivo", no "las dependencias externas
# funcionan" (eso se ve en Langfuse/CloudWatch, no en el healthcheck).
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

# backend/api/run.py (no "uvicorn backend.api.main:app" directo): fija la
# policy de asyncio ANTES de importar uvicorn — necesario en Windows, pero
# también válido en Linux/contenedor (el fix solo actúa si sys.platform ==
# "win32", así que aquí es un no-op seguro). Sin --reload: en producción no
# se quiere el watcher de archivos de uvicorn.
CMD ["python", "-m", "backend.api.run", "--host", "0.0.0.0", "--port", "8000"]
