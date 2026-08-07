"""
Servicio de acceso a datos: pedidos, historial de devoluciones, políticas (RAG) y
mutaciones sobre las devoluciones. Contiene toda la lógica que antes vivía dentro de
las funciones `@mcp.tool()` de backend/mcp/mcp_supabase.py.

Porqué esta capa existe (ver doc/AUDITORIA_RAMAS.md, punto 6): antes, la lógica de
negocio (qué tablas de Supabase consultar, cómo calcular el historial) estaba mezclada
con el código de transporte MCP (decoradores @mcp.tool(), formato de argumentos que
espera un LLM). Eso impedía reutilizar, por ejemplo, "consultar un pedido" desde un
futuro endpoint FastAPI sin arrastrar el protocolo MCP. Con esta capa, mcp_supabase.py
pasa a ser un wrapper fino que solo traduce `@mcp.tool()` -> llamada a estas funciones;
cualquier otro consumidor (FastAPI, un script, un test) puede importar directamente
desde aquí sin tocar MCP.

A diferencia de las tools MCP (ver ReturnItem en mcp_supabase.py), estas funciones no
usan modelos Pydantic para `items`: ese tipado solo hace falta en la frontera MCP,
donde un LLM con tools + response_format en modo "strict" necesita un JSON Schema
fijo (ver README.md, "Correcciones de robustez recientes"). Aquí, sin LLM de por
medio, un `list[dict]` normal es más simple y no tiene ese problema.
"""

import os
from datetime import datetime, timezone

# Cliente Supabase singleton (ver db/supabase_client.py): todas las funciones
# de este módulo lo piden con "await" antes de hacer cualquier consulta.
from backend.db.supabase_client import get_supabase_client


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def calculate_days_since_delivery(order_details: dict) -> int:
    """Calcula los días transcurridos desde la entrega del pedido.

    Usa `delivered_at` si existe, sino `created_at` como fallback.
    Devuelve 9999 si no hay ninguna fecha disponible.
    """
    # order_details tiene la forma {"order": {...}, "items": [...]}.
    order = order_details.get("order", {})
    # Prioriza la fecha real de entrega; si el pedido aún no se marcó como
    # entregado, usa la fecha de creación como aproximación razonable.
    date_str = order.get("delivered_at") or order.get("created_at")
    if not date_str:
        # Sin ninguna fecha no se puede calcular el plazo: se devuelve un
        # valor centinela enorme para que cualquier política de plazo lo
        # trate como "fuera de plazo" en vez de reventar con una excepción.
        return 9999

    # Parsear la fecha (soporta tanto +00:00 como Z)
    # datetime.fromisoformat no entiende el sufijo "Z" (UTC) de forma nativa
    # en versiones antiguas de Python, así que se normaliza a "+00:00" antes.
    date_str = date_str.replace("Z", "+00:00")
    try:
        delivered = datetime.fromisoformat(date_str)
    except ValueError:
        # Fecha con formato inesperado/corrupto: mismo fallback que "sin fecha".
        return 9999

    # now() con timezone.utc: imprescindible para poder restar contra
    # "delivered", que también lleva zona horaria (si no, Python lanza error
    # al restar un datetime "naive" con uno "aware").
    now = datetime.now(timezone.utc)
    # .days trunca a días completos (ignora horas/minutos de la diferencia).
    return (now - delivered).days


# ---------------------------------------------------------------------------
# Pedidos
# ---------------------------------------------------------------------------


async def get_order_details(order_id: str) -> dict:
    """Consulta en PostgreSQL los detalles del pedido, fechas y productos comprados.

    Args:
        order_id: UUID del pedido a consultar.
    """
    client = await get_supabase_client()

    # select con sintaxis de "join embebido" de Supabase: trae la fila de
    # "orders" y, anidado bajo la clave "customer", los campos indicados de
    # la tabla relacionada "customers" (vía foreign key).
    order_resp = await client.table("orders").select(
        "*, customer:customers(id, email, full_name)"
    ).eq("id", order_id).single().execute()
    # .single(): espera exactamente una fila y la devuelve como dict (no lista);
    # lanza error si hay 0 o más de 1 coincidencias.

    # Segunda consulta: todas las líneas de ese pedido, cada una con su
    # producto embebido (mismo patrón de join que arriba).
    items_resp = await client.table("order_items").select(
        "*, product:products(name, sku, category, price, weight_kg)"
    ).eq("order_id", order_id).execute()

    # Se combinan ambas respuestas en un único dict con la forma que
    # esperan el resto de agentes/servicios: {"order": {...}, "items": [...]}.
    return {
        "order": order_resp.data,
        "items": items_resp.data,
    }


# ---------------------------------------------------------------------------
# Historial de devoluciones
# ---------------------------------------------------------------------------


async def get_customer_return_history(customer_id: str) -> dict:
    """Recupera el historial de devoluciones del cliente para detectar posibles abusos.

    Args:
        customer_id: UUID del cliente.
    """
    client = await get_supabase_client()

    # Trae todas las solicitudes de devolución de ese cliente, ordenadas de
    # la más reciente a la más antigua, con solo las columnas necesarias.
    returns_resp = await client.table("return_requests").select(
        "id, order_id, status, reason, reason_category, resolution, refund_amount, created_at, resolved_at"
    ).eq("customer_id", customer_id).order("created_at", desc=True).execute()

    # Los contadores se calculan en Python (no en SQL) porque ya se tienen
    # todas las filas descargadas y son pocas por cliente; evita una segunda
    # ida y vuelta a la base de datos solo para contar.
    total_returns = len(returns_resp.data)
    approved = sum(1 for r in returns_resp.data if r["status"] == "approved")
    rejected = sum(1 for r in returns_resp.data if r["status"] == "rejected")

    # Este resumen (total/approved/rejected) es justo lo que usa el Agente
    # Evaluador para detectar el patrón de "cliente abusón" (>5 aprobadas).
    return {
        "customer_id": customer_id,
        "total_returns": total_returns,
        "approved": approved,
        "rejected": rejected,
        "returns": returns_resp.data,
    }


# ---------------------------------------------------------------------------
# Búsqueda RAG de políticas
# ---------------------------------------------------------------------------


async def search_return_policy(query: str, category: str = "") -> dict:
    """Realiza una búsqueda semántica RAG usando pgvector sobre la normativa de la tienda.

    Args:
        query: Texto de consulta para buscar en las políticas.
        category: Categoría opcional para filtrar políticas (e.g., "electronics").
    """
    # Import local para no cargar el SDK de OpenAI si esta función no se invoca.
    import openai

    client = await get_supabase_client()

    # Cliente de OpenAI aparte del LLM de LangChain: aquí se usa directamente
    # para pedir el embedding (vector numérico) del texto de búsqueda.
    openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    # Debe ser el mismo modelo de embedding usado al indexar las políticas.
    # Si se cambiara el modelo aquí sin re-vectorizar policy_embeddings, las
    # distancias vectoriales dejarían de tener sentido (vectores no comparables).
    embedding_resp = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=query,
    )
    # El embedding de la consulta: un vector de floats que representa su
    # significado semántico, listo para comparar contra los ya guardados.
    query_embedding = embedding_resp.data[0].embedding

    rpc_params = {
        "query_embedding": query_embedding,
        "match_threshold": 0.7,  # similitud mínima (coseno) para considerar un match.
        "match_count": 5,        # nº máximo de fragmentos de política a devolver.
    }
    # .rpc(): llama a una función SQL definida en Supabase (ver migración 011),
    # que hace la búsqueda por similitud vectorial dentro de PostgreSQL/pgvector.
    results = await client.rpc("match_policy_embeddings", rpc_params).execute()

    policy_info = None
    if category:
        # Además de los fragmentos semánticos, si se conoce la categoría del
        # producto se trae también la política "oficial" completa de esa
        # categoría (plazos, condiciones, recargos) para dar contexto exacto.
        policy_resp = await client.table("return_policies").select("*").eq(
            "category", category
        ).eq("active", True).single().execute()
        policy_info = policy_resp.data

    return {
        "query": query,
        "category": category,
        "semantic_results": results.data,
        "policy_info": policy_info,
    }


# ---------------------------------------------------------------------------
# Crear devolución
# ---------------------------------------------------------------------------


async def create_return_record(
    order_id: str,
    customer_id: str,
    reason: str,
    reason_category: str,
    refund_amount: float,
    items: list[dict],
    notes: str = "",
) -> dict:
    """Inserta una solicitud de devolución en la tabla devoluciones de Supabase.

    Args:
        order_id: UUID del pedido.
        customer_id: UUID del cliente.
        reason: Motivo de la devolución.
        reason_category: Categoría del motivo (e.g., "defective", "wrong_item").
        refund_amount: Monto del reembolso.
        items: Lista de items a devolver, cada uno con "order_item_id", "quantity"
            y opcionalmente "condition".
        notes: Notas adicionales opcionales.
    """
    client = await get_supabase_client()

    # Toda devolución nueva arranca en estado "pending".
    return_data = {
        "order_id": order_id,
        "customer_id": customer_id,
        "status": "pending",
        "reason": reason,
        "reason_category": reason_category,
        "refund_amount": refund_amount,
        "notes": notes,
    }

    # INSERT de la cabecera de la devolución; .data[0] porque Supabase
    # devuelve la(s) fila(s) insertada(s) como lista, aquí siempre una sola.
    return_resp = await client.table("return_requests").insert(return_data).execute()
    return_request = return_resp.data[0]
    # Se necesita el id recién generado para poder insertar las líneas hijas
    # (return_items) con la foreign key correcta.
    return_id = return_request["id"]

    # Construye en Python la lista de líneas a insertar, una por artículo
    # devuelto, enlazándolas todas con el return_request_id recién creado.
    return_items_data = [
        {
            "return_request_id": return_id,
            "order_item_id": item["order_item_id"],
            "quantity": item["quantity"],
            "condition": item.get("condition", "unknown"),
        }
        for item in items
    ]

    # Inserción en bloque de todas las líneas de una vez (una sola query).
    await client.table("return_items").insert(return_items_data).execute()

    return {
        "return_request": return_request,
        "items_created": len(return_items_data),
    }


# ---------------------------------------------------------------------------
# Actualizar estado de devolución
# ---------------------------------------------------------------------------


async def update_return_status(
    return_id: str,
    status: str,
    resolution: str = "",
    notes: str = "",
) -> dict:
    """Actualiza el estado de la devolución desde el panel de control manual.

    Args:
        return_id: UUID de la solicitud de devolución.
        status: Nuevo estado ("approved", "rejected", "processing", "completed").
        resolution: Resolución aplicada (e.g., "full_refund", "partial_refund", "replacement").
        notes: Notas adicionales del administrador.
    """
    client = await get_supabase_client()

    # resolution/notes solo se envían si el llamante los proporcionó, para no
    # sobrescribir con cadenas vacías valores ya guardados.
    update_data: dict = {"status": status}
    if resolution:
        update_data["resolution"] = resolution
    if notes:
        update_data["notes"] = notes
    if status in ("approved", "rejected", "completed"):
        # "now()" es una función SQL, no una fecha calculada en Python: se
        # evalúa en el servidor de PostgreSQL en el momento del UPDATE,
        # así no hay desfases de reloj entre el cliente y la base de datos.
        update_data["resolved_at"] = "now()"

    resp = await client.table("return_requests").update(update_data).eq(
        "id", return_id
    ).execute()

    # Si el id no existe, resp.data queda vacío: se devuelve None en vez de
    # lanzar un IndexError al intentar acceder a resp.data[0].
    return {"updated_return": resp.data[0] if resp.data else None}
