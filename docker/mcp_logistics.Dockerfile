# Imagen del MCP server de Logística (backend/mcp/mcp_logistics.py, puerto
# 8002) — etiquetas de envío (PDF) + notificaciones simuladas.
#
# Build de contexto = raíz del repo:
#   docker build -f docker/mcp_logistics.Dockerfile -t reflow-mcp-logistics:latest .
#
# Ver docker/api.Dockerfile para el porqué del patrón multi-stage.
FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /install /usr/local

COPY backend/ backend/

ENV PYTHONUNBUFFERED=1

EXPOSE 8002

# generated_labels/ (PDFs de etiquetas + notifications_log.jsonl) se crea
# en tiempo de ejecución vía LABELS_DIR.mkdir(exist_ok=True) en
# backend/services/logistics_service.py — no hace falta crearla aquí a
# mano. OJO al desplegar en Fargate: el filesystem del contenedor es
# efímero y NO se comparte entre tasks (ni sobrevive un redeploy/escalado).
# Ver la sección de almacenamiento persistente (EFS) en
# docs/deployment_aws_ecs_fargate.md — sin ese volumen montado, cada
# etiqueta generada se pierde en cuanto la task se recicla.

# Mismo comentario que en mcp_supabase.Dockerfile: MCP no tiene un /health
# HTTP trivial, así que el healthcheck solo valida el puerto TCP.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import socket; socket.create_connection(('127.0.0.1', 8002), timeout=3).close()"

CMD ["python", "-m", "backend.mcp.mcp_logistics"]
