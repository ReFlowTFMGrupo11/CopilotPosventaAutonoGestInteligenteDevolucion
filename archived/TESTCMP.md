# Probar los servidores MCP

Los servidores MCP (`mcp_supabase` y `mcp_logistics`) usan transporte **Streamable HTTP**, el transporte vigente del protocolo MCP (sustituye a SSE, que quedó deprecado en la spec 2025-03-26 y llegó a EOL el 1 de abril de 2026). La ruta por defecto del servidor es `/mcp` (ver `run_streamable_http_async`).

Necesitas **3 terminales** abiertas a la vez en la raíz del proyecto (`CopilotPosventaAutonoGestInteligenteDevolucion`), todas con el entorno virtual activado:

```bash
source .venv/Scripts/activate
```

## Terminal 1 — Servidor MCP Supabase (puerto 8001)

Expone las tools de datos y políticas (`get_order_details`, `get_customer_return_history`, `search_return_policy`, `create_return_record`, `update_return_status`).

```bash
source .venv/Scripts/activate
python -m backend.mcp.mcp_supabase
```

Queda escuchando en `http://localhost:8001/mcp`. Déjala abierta; no imprime nada más salvo logs de arranque de uvicorn.

## Terminal 2 — Servidor MCP Logística (puerto 8002)

Expone las tools de logística (`generate_shipping_label`, `send_customer_notification`).

```bash
source .venv/Scripts/activate
python -m backend.mcp.mcp_logistics
```

Queda escuchando en `http://localhost:8002/mcp`. Déjala abierta también.

## Terminal 3 — Ejecutar los tests (conexión real a la BBDD)

Con las dos anteriores ya arrancadas, en una tercera terminal:

```bash
source .venv/Scripts/activate
python tests/test_mcp_supabase.py
python tests/test_mcp_logistics.py
```

- `test_mcp_supabase.py`: se conecta al servidor del puerto 8001, lista las tools disponibles y llama a `get_customer_return_history` contra la base de datos real de Supabase.
- `test_mcp_logistics.py`: se conecta al servidor del puerto 8002, genera un PDF real en `generated_labels/` con `generate_shipping_label` y simula un envío con `send_customer_notification`.

### Nota Windows: emojis en consola

Los scripts imprimen emojis (🔧, 📋, 📦, 📧). La consola de Windows por defecto usa el codepage `cp1252` y no puede mostrarlos, lo que provoca `UnicodeEncodeError`. Si te pasa, lanza los tests así:

```bash
PYTHONIOENCODING=utf-8 python tests/test_mcp_supabase.py
PYTHONIOENCODING=utf-8 python tests/test_mcp_logistics.py
```

(`mcp_logistics.py` ya fuerza UTF-8 internamente para que el propio servidor no falle al loguear `send_customer_notification`; el `PYTHONIOENCODING` de arriba es solo para el proceso del test/cliente en tu terminal.)

## Parar los servidores

`Ctrl+C` en cada una de las terminales 1 y 2.

## Errores comunes

### `[Errno 10048] error while attempting to bind on address ('0.0.0.0', 8001)` (o `8002`)

```
ERROR:    [Errno 10048] error while attempting to bind on address ('0.0.0.0', 8001): [winerror 10048] solo se permite un uso de cada dirección de socket (protocolo/dirección de red/puerto)
```

**Causa:** ya hay otro proceso escuchando en ese puerto — normalmente una instancia anterior de `mcp_supabase.py` o `mcp_logistics.py` que quedó corriendo (p. ej. lanzada en segundo plano y nunca cerrada con `Ctrl+C`).

**Solución:** localizar el proceso que ocupa el puerto y matarlo, luego reintentar.

```bash
# Ver qué PID está escuchando en el puerto (cambia 8001 por 8002 si aplica)
netstat -ano | grep ":8001" | grep LISTENING

# Matar ese proceso (sustituye <PID> por el número de la última columna)
taskkill //PID <PID> //F

# Volver a arrancar el servidor
python -m backend.mcp.mcp_supabase
```
