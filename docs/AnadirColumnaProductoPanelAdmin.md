# Añadir columna "Producto" al panel de administración

## Petición

En el Panel de administración (`/admin`), tanto la tabla "Pendientes de
aprobación" como "Todas las devoluciones" mostraban `Pedido`, `Cliente`
(UUID), `Importe`, `Motivo` y `Estado`, pero no qué producto/s se estaban
devolviendo. Se pidió añadir una columna "Producto" en ambas tablas.

## Causa de que faltara

Las consultas a Supabase en `list_pending_approvals` y `list_returns`
(`backend/services/supabase_service.py`) solo seleccionaban columnas propias
de `return_requests` más el join a `orders(order_number)`. Nunca se unía con
`return_items` (que enlaza la devolución con los artículos concretos vía
`order_item_id`), así que el dato del producto no llegaba ni siquiera hasta
el backend, y mucho menos al frontend.

## Cambios implementados

### 1. `backend/services/supabase_service.py` — join hasta `products` + nuevo helper de aplanado

**Dónde:** funciones `list_pending_approvals` y `list_returns`.

**Qué se añadió:** a la query de Supabase se le añadió el embed anidado
```
return_items(order_items(product:products(name)))
```
que sigue la misma cadena de claves foráneas que ya usa `get_order_details`
(`order_items` → `product:products(...)`), aplicada aquí a través de
`return_items.order_item_id`.

Se añadió un nuevo helper:
```python
def _flatten_product_names(row: dict) -> dict:
    items = row.pop("return_items", None) or []
    names = [
        product.get("name")
        for item in items
        for product in [(item.get("order_items") or {}).get("product") or {}]
        if product.get("name")
    ]
    row["product_names"] = ", ".join(names) if names else None
    return row
```
y un `_flatten_admin_row(row)` que encadena `_flatten_order_number` +
`_flatten_product_names`, usado en ambas funciones en vez de llamar a
`_flatten_order_number` directamente.

**Por qué:**
- El embed de PostgREST devuelve el join anidado (`row["return_items"][i]["order_items"]["product"]["name"]`),
  no un campo plano; hacía falta aplanarlo igual que ya se hacía con
  `order_number`, siguiendo el mismo patrón existente en el archivo en vez de
  introducir uno nuevo.
- Se une con `", "` en un solo string (`product_names`) porque una misma
  devolución puede incluir **varios artículos** (pedidos mixtos, ver
  [ArreglarRepeticionEstadoPedidosMixtos.md](ArreglarRepeticionEstadoPedidosMixtos.md)),
  y la tabla del admin muestra una fila por devolución, no por artículo.

### 2. `frontend/pages/1_Admin.py` — nueva columna "Producto"

**Dónde:** las dos tablas, "Pendientes de aprobación" (columnas manuales con
`st.columns`) y "Todas las devoluciones" (`st.dataframe`).

**Qué se añadió:**
- En "Pendientes de aprobación": nueva columna entre `Cliente` e `Importe`,
  tanto en el header (`st.columns([2, 2, 2.2, 1.3, 3, 2.2, 1, 1])`, ancho
  `2.2`) como en cada fila (`c3.write(row.get("product_names") or "—")`),
  desplazando el resto de columnas (Importe, Motivo, Motivo decisión,
  Aprobar, Rechazar) una posición.
- En "Todas las devoluciones": nueva clave `"Producto": r.get("product_names") or "—"`
  en el dict de cada fila, entre `Cliente` e `Importe`.

**Por qué:** coloca la columna en el mismo sitio que se pidió (justo después
de `Cliente`), reutilizando el campo `product_names` ya aplanado por el
backend; sin cambios adicionales en `frontend/lib/api.py` porque
`pending_returns()`/`list_returns()` ya devuelven el JSON tal cual llega del
backend.

## Validación pendiente

Arrancar backend + frontend contra Supabase y comprobar visualmente que:
- Las devoluciones de un solo artículo muestran su nombre de producto.
- Las devoluciones de pedidos mixtos (varios artículos) muestran los nombres
  separados por coma.
- Devoluciones sin `return_items` (si las hubiera) muestran "—" en vez de
  romper la tabla.
