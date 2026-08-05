# Defender la arquitectura MCP de ReFlow

Este documento recoge los argumentos para defender, en la memoria/presentación del TFM,
las dos decisiones de arquitectura tomadas para la capa MCP de ReFlow: separar las
herramientas en servidores independientes por dominio, y construirlos con FastMCP en
lugar de implementar el protocolo desde cero.

## 1. Arquitectura: un servidor MCP independiente por dominio funcional

### El planteamiento
ReFlow separa las herramientas en dos servidores MCP según su dominio (`backend/mcp/`):

- **`mcp_supabase.py`** (puerto 8001): datos y conocimiento — acceso a PostgreSQL
  (pedidos, clientes, devoluciones) y búsqueda semántica RAG sobre pgvector.
- **`mcp_logistics.py`** (puerto 8002): acciones externas — generación de etiquetas de
  transporte (PDF) y notificaciones al cliente.

En el MVP actual ambos se ejecutan como procesos Python independientes en local (ver
[`README.md`](README.md)), pero el diseño está pensado para que cada uno pueda desplegarse
en su propio contenedor Docker en producción sin cambiar una línea de sus tools.

### Argumentos para defenderlo
- **Aislamiento de fallos:** Si `mcp_logistics` (que en producción llamaría a una agencia
  de transporte real) falla o se satura, `mcp_supabase` sigue respondiendo consultas de
  pedidos y políticas con normalidad. El agente de resolución puede seguir operando sobre
  los datos aunque la parte logística esté degradada.
- **Seguridad y principio de menor privilegio:** `mcp_supabase` es el único proceso con la
  `SUPABASE_SERVICE_KEY`; `mcp_logistics` no necesita ninguna credencial de base de datos,
  solo acceso al directorio `generated_labels/`. Si se compromete uno, el otro no expone
  credenciales que no necesita.
- **Independencia de dependencias:** `mcp_logistics` depende de `reportlab` (generación de
  PDF); `mcp_supabase` depende del SDK de `supabase` y de `openai` (embeddings para RAG).
  Mantenerlos separados evita que un servidor cargue dependencias pesadas que no usa.
- **Despliegues y actualizaciones atómicas:** En producción, un cambio en la lógica de
  generación de etiquetas se despliega reiniciando solo el contenedor de logística, sin
  tocar el servicio de datos que sí necesita alta disponibilidad.

## 2. El núcleo del desarrollo: ¿por qué FastMCP?

### El planteamiento
Implementar MCP desde cero obliga a manejar JSON-RPC, sesiones y validación de esquemas a
mano. ReFlow usa `FastMCP` (`mcp.server.fastmcp.FastMCP`, incluido en el SDK oficial `mcp`
del protocolo), una capa de alto nivel inspirada en FastAPI que abstrae esa complejidad.

> **Nota de versión:** el SDK `mcp` lanzó una versión 2.x que reestructuró su API interna
> (`FastMCP` pasó a llamarse `MCPServer` en otro módulo). ReFlow fija `mcp[cli]<2.0.0` en
> `requirements.txt` para mantener la API estable usada en `mcp_supabase.py` y
> `mcp_logistics.py`.

### Argumentos para defenderlo
- **Desarrollo pythonico y menos boilerplate:** con el decorador `@mcp.tool()` se expone
  una función `async` de Python como herramienta MCP sin escribir lógica de protocolo a
  mano, tal y como hacen `generate_shipping_label` y `get_customer_return_history` en este
  repo.
- **Generación automática de esquemas:** FastMCP usa las anotaciones de tipos y los
  docstrings de la función para generar el JSON Schema que el LLM necesita para invocar la
  tool. Basta con tipar `order_id: str` para que FastMCP valide la entrada.
- **Transporte Streamable HTTP integrado:** `mcp.run(transport="streamable-http")` expone
  el servidor por HTTP sin montar manualmente un servidor ASGI, que es justo lo que usan
  ambos servidores de ReFlow en `http://localhost:800{1,2}/mcp`.

## 3. Preguntas frecuentes y objeciones comunes

### Objeción: "¿No es excesivo un contenedor Docker por cada MCP? Añade complejidad de red."
No es sobrecarga, es modularidad: Docker Compose gestionaría la red interna y los
contenedores se comunicarían localmente. Durante el desarrollo del MVP se ha optado
deliberadamente por ejecutar ambos servidores como procesos locales (más rápido de iterar,
sin overhead de red), dejando la contenerización como el paso natural al pasar a
producción, sin que cambie el código de las tools.

### Objeción: "¿Por qué no meter todo en un solo script de Python grande?"
Eso genera deuda técnica: un monolito acopla el acceso a Supabase con la generación de
PDFs y el envío de notificaciones. Separando `mcp_supabase.py` y `mcp_logistics.py`, cada
uno se prueba (`tests/test_mcp_supabase.py`, `tests/test_mcp_logistics.py`) y se mantiene
por separado.

### Objeción: "¿FastMCP añade latencia o restricciones?"
Al contrario: FastMCP abstrae la complejidad del protocolo MCP de bajo nivel (sesiones,
JSON-RPC, streaming) y reduce bugs de integración entre el LLM y el backend, acelerando el
desarrollo del MVP.

## 4. Ejemplo real del repo (`mcp_logistics.py`, simplificado)

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("logistics", host="0.0.0.0", port=8002)

@mcp.tool()
async def generate_shipping_label(order_id: str, items: list[dict]) -> dict:
    """Genera un PDF simulado de etiqueta de transporte para una devolución."""
    tracking_number = f"RF-{order_id[:8].upper()}"
    # ... generación del PDF con reportlab ...
    return {"tracking_number": tracking_number}

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

## 5. Resumen para la presentación

> "Optamos por separar las herramientas en dos servidores MCP independientes — datos y
> políticas (Supabase/pgvector) por un lado, logística por otro — para garantizar
> aislamiento de fallos y menor privilegio de credenciales entre dominios. En el MVP los
> ejecutamos como procesos locales sobre Streamable HTTP para iterar rápido, pero el
> diseño permite contenerizar cada uno de forma independiente en producción sin tocar su
> lógica interna. Para el desarrollo usamos FastMCP, la capa oficial del SDK `mcp` que
> convierte funciones Python tipadas en herramientas MCP listas para agentes de IA, sin
> escribir el protocolo JSON-RPC a mano."
