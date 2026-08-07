"""Re-export de ReturnState desde backend.models.state.

Mantiene compatibilidad con imports existentes:
    from backend.agents.state import ReturnState
"""

# La definición real de ReturnState vive en backend/models/state.py; este
# archivo solo la vuelve a exportar aquí para no romper el código (nodos,
# tests) que ya la importa desde "backend.agents.state".
from backend.models.state import ReturnState

# Documenta explícitamente que ReturnState es el único símbolo público de
# este módulo.
__all__ = ["ReturnState"]
