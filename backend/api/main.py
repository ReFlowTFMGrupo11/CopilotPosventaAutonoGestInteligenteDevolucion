"""
FastAPI backend para ReFlow.

Endpoints:
- /api/chat       → Interacción con el grafo de agentes (LangGraph)
- /api/admin      → Panel de gestión y HITL
- /api/orders     → Consultas de pedidos y clientes (directo a services)
- /api/stats      → KPIs del sistema
- /health         → Health check

Ejecutar:
    uvicorn backend.api.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv(override=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.agents.graph import get_return_graph
from backend.api.routers import admin, chat, orders
from backend.services.observability import flush as langfuse_flush, get_langfuse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: pre-construye el grafo para que el primer request no espere."""
    app.state.graph = await get_return_graph()
    # Verificar conexión LangFuse al arrancar
    lf = get_langfuse()
    if lf:
        lf.trace(name="app_startup", metadata={"version": "0.1.0"})
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


@app.get("/health")
async def health_check():
    """Verifica que el backend está vivo."""
    return {"status": "ok", "service": "reflow-api"}
