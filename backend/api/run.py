"""
Punto de entrada para arrancar la API sin el hang de 30s en Windows.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 POR QUÉ ESTE MÓDULO EXISTE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

`uvicorn backend.api.main:app` (sin --reload) crea su event loop DENTRO de
``Server.run()``:

    asyncio_run(self.serve(sockets=sockets), loop_factory=self.config.get_loop_factory())

``self.serve(sockets=sockets)`` solo construye el objeto corrutina; su
cuerpo (que incluye ``config.load()``, el import real de ``backend.api.main``
y, con él, el ``asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())``
de ``backend/agents/graph.py``) no se ejecuta hasta que ``asyncio_run`` ya
arrancó el loop. En Windows, sin ``--reload``, ese loop se crea vía
``uvicorn.loops.asyncio.asyncio_loop_factory()``, que devuelve
``asyncio.ProactorEventLoop`` explícitamente (no consulta la policy en
absoluto). Resultado: el fix de ``graph.py`` llega siempre demasiado tarde
para este camino, y ``AsyncPostgresSaver`` tarda 30s reintentando contra
Postgres antes de caer a ``InMemorySaver`` (sin persistencia entre
reinicios).

Con ``--reload`` (o ``--workers`` > 1) el problema no se nota porque uvicorn
usa ``SelectorEventLoop`` en ese caso — pero es un efecto colateral de cómo
gestiona los subprocesos de recarga (``use_subprocess=True``), no una
garantía: un arranque en producción sin ``--reload`` seguía afectado.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 EL FIX
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Fijar la policy AQUÍ, antes de importar ``uvicorn`` siquiera, garantiza que
ya está activa cuando ``asyncio_run`` cree el loop. Y pasar ``loop="none"``
le dice a uvicorn que no fuerce su propio loop_factory (que ignoraría la
policy): con ``loop_factory=None``, ``asyncio.Runner`` crea el loop con
``asyncio.new_event_loop()``, que sí respeta la policy activa.

Uso (sustituye a ``uvicorn backend.api.main:app [--reload] --port 8000``):
    python -m backend.api.run [--reload] [--port 8000] [--host 0.0.0.0]
"""

from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Arranca la API FastAPI de ReFlow.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run(
        "backend.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        loop="none",
    )


if __name__ == "__main__":
    main()
