"""
Estado compartido del grafo de devoluciones.

Define el TypedDict que fluye entre los tres agentes (Triaje, Evaluador, Resolución)
y las aristas condicionales del grafo LangGraph.
"""

# Permite usar anotaciones de tipo modernas (p. ej. "str | None") sin que
# Python las evalúe en tiempo de importación.
from __future__ import annotations

# Annotated: permite "etiquetar" un tipo con metadatos extra (aquí, el reducer).
# Any: tipo comodín cuando el contenido puede ser cualquier cosa (p. ej. un dict libre).
from typing import Annotated, Any

# Tipo base de LangChain para cualquier mensaje de la conversación
# (HumanMessage, AIMessage, SystemMessage, etc.).
from langchain_core.messages import AnyMessage

# Función "reducer": le dice a LangGraph cómo combinar el valor nuevo que
# devuelve un nodo con el valor que ya había en el estado para esta clave.
from langgraph.graph.message import add_messages

# TypedDict: permite definir un diccionario con claves y tipos fijos (como una
# interfaz), en vez de una clase Pydantic completa.
from typing_extensions import TypedDict


# total=False → ninguna clave es obligatoria: cada agente solo rellena las
# claves que le corresponden, el resto pueden faltar sin error.
class ReturnState(TypedDict, total=False):
    """Estado global del grafo de devoluciones.

    Cada agente lee las claves que necesita y escribe solo las que actualiza.
    ``messages`` usa el reducer ``add_messages`` para acumular el historial
    de la conversación sin sobrescribirlo.
    """

    # ── Historial de conversación ──────────────────────────────────────
    # Annotated[..., add_messages]: en vez de que el mensaje nuevo devuelto
    # por un nodo SUSTITUYA la lista completa, LangGraph usa add_messages
    # para ANEXARLO al historial existente (y fusionar por id si coincide).
    messages: Annotated[list[AnyMessage], add_messages]

    # ── Datos extraídos por el Agente de Triaje ────────────────────────
    order_id: str | None            # UUID del pedido que el cliente quiere devolver.
    customer_id: str | None         # UUID del cliente, se rellena tras consultar el pedido.
    customer_name: str | None       # Nombre completo, para personalizar mensajes/etiqueta.
    customer_email: str | None      # Email, para la notificación simulada.
    reason: str | None              # Motivo de la devolución en texto libre del cliente.
    reason_category: str | None     # Motivo normalizado: defective, wrong_item, etc.
    items_to_return: list[dict[str, Any]]  # Artículos a devolver (order_item_id, quantity, condition).

    # ── Datos del pedido (rellenados tras consultar Supabase) ──────────
    order_details: dict[str, Any] | None   # Pedido + líneas + productos (desde get_order_details).
    return_history: dict[str, Any] | None  # Historial de devoluciones previas del cliente.

    # ── Resultado del Agente Evaluador ─────────────────────────────────
    is_eligible: bool | None           # True/False: ¿se puede devolver según la política?
    eligibility_reason: str | None     # Explicación textual de la decisión (para el rechazo/aprobación).
    policy_info: dict[str, Any] | None # Resultados crudos de la búsqueda RAG sobre políticas.
    refund_amount: float               # Importe a reembolsar (0 si no es elegible).
    # days_since_delivery/policy_max_return_days: mismos datos que usa
    # policy.py para razonar el plazo, reexpuestos en el estado porque
    # resolution.py los necesita para detectar la "zona frontera" del plazo
    # (dataset/policies/00_marco_general_devoluciones.md, sección 5) sin
    # tener que recalcularlos.
    days_since_delivery: int | None
    policy_max_return_days: int | None

    # ── Resultado del Agente de Resolución ─────────────────────────────
    needs_admin_approval: bool       # True si el importe supera el umbral HITL.
    admin_decision: str | None       # "approved" | "rejected" | None — decisión humana en HITL.
    tracking_number: str | None      # Código de seguimiento de la etiqueta generada.
    label_path: str | None           # Ruta local al PDF de la etiqueta generada.
    return_request_id: str | None    # UUID de la fila insertada en return_requests.
    resolution: str | None           # Resultado final: "approved", "rejected", "rejected_by_admin"...

    # ── Control de flujo ───────────────────────────────────────────────
    current_agent: str | None  # Nombre del último nodo/agente que actuó (para depuración/UI).
    error: str | None          # Mensaje de error si algo falló (p. ej. pedido no encontrado).
