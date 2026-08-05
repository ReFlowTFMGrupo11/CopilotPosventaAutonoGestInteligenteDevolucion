"""Re-export de ReturnState desde backend.models.state.

Mantiene compatibilidad con imports existentes:
    from backend.agents.state import ReturnState
"""

from backend.models.state import ReturnState

__all__ = ["ReturnState"]
