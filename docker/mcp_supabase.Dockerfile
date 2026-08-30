# Imagen del MCP server de Supabase (backend/mcp/mcp_supabase.py, puerto
# 8001) — CRUD de pedidos/devoluciones + búsqueda RAG de políticas.
#
# Build de contexto = raíz del repo:
#   docker build -f docker/mcp_supabase.Dockerfile -t reflow-mcp-supabase:latest .
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

EXPOSE 8001

# No hay un endpoint HTTP simple tipo /health en el protocolo MCP (FastMCP
# expone /mcp con streamable-HTTP, que espera cabeceras de sesión MCP, no
# un GET a pelo) — el healthcheck aquí solo comprueba que el puerto acepta
# conexiones TCP, no que el protocolo MCP responda bien. Es la misma
# limitación que se traslada al healthCheck del contenedor en la task
# definition de ECS (ver docs/deployment_aws_ecs_fargate.md).
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import socket; socket.create_connection(('127.0.0.1', 8001), timeout=3).close()"

CMD ["python", "-m", "backend.mcp.mcp_supabase"]
