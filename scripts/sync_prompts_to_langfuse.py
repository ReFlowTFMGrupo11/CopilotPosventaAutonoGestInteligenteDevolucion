"""
Sincroniza con Langfuse los prompts de sistema que viven como constantes
Python en backend/agents/nodes/*.py.

## Diseño: el código sigue siendo la fuente de verdad, Langfuse es un espejo

A diferencia de un uso "completo" de Langfuse Prompt Management (donde los
agentes leerían el prompt de Langfuse en tiempo de ejecución, con fallback
local si Langfuse no está disponible), aquí se hizo la elección contraria a
propósito: los agentes (triage.py/evaluator.py/resolution.py) siguen
importando y usando sus constantes de Python exactamente igual que antes --
CERO cambios en su lógica ni en su disponibilidad. Este script solo EMPUJA
el contenido actual del código hacia Langfuse, nunca al revés.

Motivo: mantener el prompt versionado y editable en Langfuse (útil para
"Link to Traces"/métricas por versión, más adelante) sin renunciar a que un
prompt sea código *source controlled* -- revisable en PR, con historia de
git real, sin depender de que alguien recuerde sincronizar de vuelta un
cambio hecho a mano en la UI de Langfuse antes de que se pierda.

## Qué hace

Por cada prompt de la tabla `PROMPTS` (nombre en Langfuse -> constante
Python), comprueba si la versión ya etiquetada `production` en Langfuse
tiene EXACTAMENTE el mismo texto que la constante actual:
  - Si coincide: no hace nada (evita crear una versión nueva idéntica en
    cada ejecución -- Langfuse crea una versión nueva en cada
    `create_prompt()`, con el mismo nombre, aunque el contenido no cambie).
  - Si no coincide (o el prompt no existe todavía en Langfuse): crea una
    versión nueva y la etiqueta `production`.

Uso:
    python -m scripts.sync_prompts_to_langfuse             # sincroniza los 4
    python -m scripts.sync_prompts_to_langfuse --dry-run   # solo muestra qué cambiaría

Cuándo ejecutarlo: cada vez que se edite una de las 4 constantes de prompt
en el código (parte del flujo de PR, no de CI -- ver README de este
directorio).

Requisitos:
    LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY en .env (mismo proyecto de
    Langfuse Cloud que ya usa backend/services/observability.py).

## Placeholders: Python str.format() -> sintaxis {{var}} de Langfuse

`REJECTION_SYSTEM_PROMPT` tiene un placeholder `{reason}` resuelto con
`.format(reason=...)` en el código (ver resolution.py) -- eso NO se toca, es
la fuente de verdad. Al subirlo a Langfuse se convierte a `{{reason}}`
(sintaxis de Langfuse) solo en la copia que se sube, para que la UI lo
reconozca como variable de plantilla en vez de texto literal con llaves.
"""

from __future__ import annotations

import argparse
import logging

from dotenv import load_dotenv

load_dotenv(override=True)

from backend.agents.nodes.evaluator import POLICY_SYSTEM_PROMPT  # noqa: E402
from backend.agents.nodes.resolution import (  # noqa: E402
    REJECTION_SYSTEM_PROMPT,
    RESOLUTION_SYSTEM_PROMPT,
)
from backend.agents.nodes.triage import TRIAGE_SYSTEM_PROMPT  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

# nombre en Langfuse -> contenido actual en el código (fuente de verdad).
# REJECTION_SYSTEM_PROMPT convierte su único placeholder de str.format()
# ("{reason}") a la sintaxis de Langfuse ("{{reason}}") solo en esta copia.
PROMPTS: dict[str, str] = {
    "triage-system-prompt": TRIAGE_SYSTEM_PROMPT,
    "policy-system-prompt": POLICY_SYSTEM_PROMPT,
    "resolution-system-prompt": RESOLUTION_SYSTEM_PROMPT,
    "rejection-system-prompt": REJECTION_SYSTEM_PROMPT.replace(
        "{reason}", "{{reason}}"
    ),
}


def _current_production_text(lf, name: str) -> str | None:
    """Texto de la versión `production` actual en Langfuse, o None si el
    prompt no existe todavía."""
    try:
        prompt = lf.get_prompt(name, label="production", cache_ttl_seconds=0)
    except Exception:
        return None
    return prompt.prompt


def sync(dry_run: bool = False) -> dict[str, str]:
    """Sincroniza los 4 prompts.

    Returns:
        Dict ``{nombre: "sin cambios"|"creado"|"actualizado"}``.
    """
    from langfuse import Langfuse

    lf = Langfuse()
    result: dict[str, str] = {}

    for name, local_text in PROMPTS.items():
        remote_text = _current_production_text(lf, name)
        if remote_text == local_text:
            result[name] = "sin cambios"
            logger.info("%-25s sin cambios (ya coincide con el código)", name)
            continue

        action = "creado" if remote_text is None else "actualizado"
        result[name] = action
        if dry_run:
            logger.info("%-25s %s (--dry-run, no se sube nada)", name, action)
            continue

        lf.create_prompt(
            name=name,
            type="text",
            prompt=local_text,
            labels=["production"],
        )
        logger.info("%-25s %s → nueva versión 'production' en Langfuse", name, action)

    if not dry_run:
        lf.flush()
    return result


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra qué cambiaría sin subir nada a Langfuse.",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    summary = sync(dry_run=args.dry_run)
    logger.info("─" * 60)
    for name, action in summary.items():
        logger.info("%-25s %s", name, action)
