"""
FastAPI backend para ReFlow.

Endpoints:
- /api/chat       → Interacción con el grafo de agentes (LangGraph)
- /api/admin      → Panel de gestión y HITL
- /api/orders     → Consultas de pedidos y clientes (directo a services)
- /api/stats      → KPIs del sistema
- /health         → Health check

Ejecutar:
    python -m backend.api.run --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv(override=True)

# Sin esto, el logger raíz de Python queda en su nivel por defecto (WARNING):
# los logger.info(...) de todo el proyecto (confirmación del checkpointer
# elegido en graph.py, inicialización de LangFuse en observability.py,
# creación de clientes MCP en mcp_client.py...) se descartan en silencio y
# nunca aparecen en los logs, aunque el código los emita. Solo se veían los
# logger.warning()/.error() (por eso los fallos sí eran visibles, pero no
# la confirmación de que algo arrancó bien).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.agents.graph import get_checkpointer_status, get_return_graph
from backend.api.routers import admin, chat, orders
from backend.services.observability import flush as langfuse_flush, get_langfuse

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: pre-construye el grafo para que el primer request no espere."""
    app.state.graph = await get_return_graph()
    # Verificar conexión LangFuse al arrancar
    lf = get_langfuse()
    if lf:
        lf.create_event(name="app_startup", metadata={"version": "0.1.0"})
    yield
    # Shutdown: vaciar el buffer de LangFuse antes de cerrar
    langfuse_flush()


app = FastAPI(
    title="ReFlow API",
    description="Copiloto de Posventa Autónomo — API de chat, admin y consultas.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS para Streamlit u otros frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(chat.router)
app.include_router(admin.router)
app.include_router(orders.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Red de seguridad final: garantiza una respuesta JSON ante CUALQUIER
    excepción no capturada por el endpoint (p. ej. admin.py tiene rutas de
    solo lectura sin try/except propio). Sin esto, FastAPI ya devuelve un 500,
    pero sin log centralizado ni formato consistente para el frontend.
    """
    logger.exception("Excepción no manejada en %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno inesperado. Inténtalo de nuevo más tarde."},
    )


@app.get("/health")
async def health_check():
    """Verifica que el backend está vivo.

    Incluye el estado del checkpointer (ver backend/agents/graph.py):
    ``persistent=False`` significa que el grafo está corriendo sobre
    ``InMemorySaver`` — el estado multi-turno y las pausas HITL no
    sobreviven a un reinicio del proceso. En development esto es normal
    sin Postgres levantado; en production nunca debería verse (el arranque
    falla antes de llegar aquí si ocurre, ver `_fail_or_degrade`).
    """
    return {
        "status": "ok",
        "service": "reflow-api",
        "checkpointer": get_checkpointer_status(),
    }
