# Auditoría: `feature/MCP_Agent_CCS` vs `agentes-tamara-testing`

Comparación técnica de las dos ramas que implementan el sistema multi-agente de
ReFlow, para decidir qué se lleva a una rama final única. Generado en la rama
`auditoria/mcp-agent-vs-tamara-testing`.

- **Rama A — `feature/MCP_Agent_CCS`**: 3 agentes independientes (`create_agent` de
  LangChain 1.x) encadenados por un script demo, con un motor de decisión determinista
  validado contra un dataset sintético de 480 casos.
- **Rama B — `agentes-tamara-testing`**: un único grafo de LangGraph (`StateGraph`) con
  6 nodos, memoria conversacional persistente (checkpointer) y HITL nativo con
  `interrupt()`.
- **Antepasado común**: commit [`f60d950`](../../commit/f60d950) ("Align project docs
  with actual repo state"). En ese punto **ninguna de las dos ramas tenía todavía** ni
  el sistema multi-agente ni el dataset — cada una construyó su propia solución desde
  cero, en direcciones distintas. Por eso el diff entre ambas es tan grande (81 archivos,
  +3043/-15528 líneas): no es que una rama "borrara" cosas de la otra, es que
  divergieron pronto y cada una añadió su propio universo de archivos.

## Resumen ejecutivo

| | Rama A (`MCP_Agent_CCS`) | Rama B (`agentes-tamara-testing`) |
|---|---|---|
| Orquestación | 3 agentes `create_agent` independientes + script que los encadena | 1 `StateGraph` de LangGraph con 6 nodos y aristas condicionales |
| Memoria entre turnos | Manual (`history` reenviado en cada llamada), sin persistencia | Checkpointer de LangGraph (Postgres o memoria), por `thread_id` |
| Decisión de elegibilidad | Función Python determinista, validada 1:1 contra 480 casos etiquetados | LLM devuelve JSON en texto libre, parseado con regex; sin dataset de validación |
| HITL (>100€) | Se detiene y deja el caso "pendiente"; no hay forma de reanudarlo en código | `interrupt()` + `Command(resume=...)`: el grafo se pausa y continúa de verdad |
| Capa de negocio vs. transporte MCP | Mezcladas: la lógica de Supabase/PDF vive dentro de los `@mcp.tool()` | Separadas: `services/` con la lógica, `mcp/` como wrapper fino |
| Selección de tool a ejecutar | El LLM decide cuándo llamar a cada tool (`create_agent(tools=[...])`) | Python decide siempre; el LLM solo redacta texto o extrae datos |
| Tests | 100% en verde (`pytest agenteNConMCP/tests`), incluida validación contra el dataset | **Rotos hoy**: 4 de 7 ficheros importan módulos que ya no existen tras un refactor |
| Corpus de políticas para RAG | 16 ficheros markdown curados + generador de dataset sintético | No incluido en la rama (solo lo que haya sembrado en Supabase) |
| Documentación | READMEs por agente + `doc/FLUJO_CONVERSACIONAL.md` + `defenderMCP.md` | `defenderAgentes.md` + `docs/graph_diagram.md` + `docs/ER_diagram.md` |
| Generación LangChain | 1.x (`langchain.agents.create_agent`) | LangGraph de bajo nivel, sin `create_agent` |

**Conclusión corta**: la Rama B tiene mejores ideas de **arquitectura de plomería**
(persistencia, HITL real, separación de capas). La Rama A tiene mejor **motor de
negocio** (determinismo, tests verdes, validación contra dataset). Ninguna gana en
todo — se explica el porqué en detalle más abajo.

## En qué confluyen (convergen)

1. **Mismo reparto de responsabilidades**: Triaje y Empatía → Evaluador de Políticas →
   Resolución y Logística. Los nombres, el orden y el objetivo de cada "agente" son
   prácticamente idénticos en ambas ramas — confirma que el diseño funcional de
   `doc/guia.md` (Épica 2) se entendió igual por los dos.
2. **Mismo modelo de datos**: las dos ramas consultan las mismas tablas de Supabase
   (`orders`, `order_items`, `customers`, `return_requests`, `return_policies`) y el
   mismo RPC de pgvector (`match_policy_embeddings`).
3. **Mismo catálogo de tools MCP**: `get_order_details`, `get_customer_return_history`,
   `search_return_policy`, `create_return_record`, `update_return_status`,
   `generate_shipping_label`, `send_customer_notification` — con firmas casi idénticas.
4. **Mismo umbral HITL**: 100 € como línea que separa aprobación automática de revisión
   manual, en ambos casos como una constante explícita en código (no en base de datos).
5. **Mismo transporte**: dos servidores MCP independientes por Streamable HTTP (Supabase
   en 8001, Logística en 8002), cada uno documentado con un argumentario de defensa de
   arquitectura (`defenderMCP.md` / `defenderAgentes.md`).
6. **Mismo principio declarado**: las dos ramas afirman explícitamente que "el LLM no
   debe decidir todo solo" — aunque, como se ve más abajo, lo aplican con rigor muy
   distinto.

## En qué distan (divergen)

### 1. Paradigma de orquestación: 3 agentes sueltos vs. 1 grafo único

Rama A usa `create_agent(...)` de LangChain 1.x tres veces, cada una construyendo su
propio bucle "modelo → tools → modelo" (ver
[`doc/FLUJO_CONVERSACIONAL.md`](FLUJO_CONVERSACIONAL.md)), y algo externo (hoy,
`demo_flujo_completo.py`) decide cuándo pasar del Agente 1 al 2 y al 3.

Rama B modela el flujo completo como un único `StateGraph` (`backend/agents/graph.py`)
con 6 nodos (`triage`, `fetch_order_data`, `evaluator`, `resolver`, `reject`,
`hitl_admin`) y aristas condicionales (`route_after_triage`, `route_after_fetch`,
`route_after_evaluator`). Es una API de más bajo nivel que `create_agent` (no forma
parte de LangChain 1.x, es LangGraph "a pelo"), pero le da control fino sobre bucles
(volver a pedir información al cliente) y ramas que `create_agent` no expone.

**Trade-off**: el grafo único es más expresivo, pero también es un cambio de paradigma
completo — no se puede "importar un trocito" sin reescribir cómo se invoca todo el
sistema.

### 2. Memoria conversacional: reenviar el historial vs. checkpointer

Rama A reconstruye el historial de mensajes a mano en cada llamada
(`run_agent_triaje(message, history=...)`) y no persiste nada entre procesos: si el
proceso se reinicia, la conversación se pierde.

Rama B usa el checkpointer de LangGraph (`InMemorySaver` en desarrollo,
`AsyncPostgresSaver` en producción) asociado a un `thread_id`: el estado completo
(`ReturnState`, incluidos los mensajes) se guarda tras cada turno y se recupera solo con
volver a invocar el grafo con el mismo `thread_id`. Además añade una capa de analítica
(`chat_sessions` / `chat_messages` vía `session_tracker.py`) para trazabilidad de
sesiones completas.

**Esto es una mejora real y no trivial** de Rama B: la propuesta de TFM
(`propuesta1.pdf`) y `doc/guia.md` dan por hecho un chat con memoria persistente, y Rama
A hoy no lo tiene resuelto en ningún punto del código.

### 3. El corazón del negocio: ¿quién decide si la devolución es válida?

Esta es la diferencia más importante y la que más pesa en la decisión final.

- **Rama A**: `_apply_deterministic_decision` + `_classify_return` en
  `agente2ConMCP/agente_evaluacion.py` son **funciones Python puras**. El LLM solo
  llama a las 3 tools y transcribe lo que devuelven; nunca decide `decision`,
  `eligible` ni `refund_amount`. Esta función está **validada 1:1 contra 408 de los 480
  casos** de `dataset/eval_cases.csv` (un dataset sintético generado y etiquetado a
  propósito), y sus tests son parte de la suite verde del repo.
- **Rama B**: `policy_evaluator_agent` en `backend/agents/nodes/policy.py` le pide al
  LLM que responda con un bloque ```` ```json ... ``` ```` en medio de texto libre, y
  luego lo extrae con una expresión regular (`re.search(r"```json\s*(.*?)\s*```", ...)`
  ). Si el LLM no incluye el bloque, o lo redacta con una coma de más, el resultado cae
  al `except` y la devolución se marca como no elegible por defecto — funciona, pero es
  frágil: **la decisión de negocio (dinero, plazos, aprobación) vive dentro de un
  prompt**, no en código verificable, y no hay ningún dataset ni test que compare sus
  veredictos contra un conjunto de casos conocido.

Ni las reglas de "zona frontera del plazo", ni "motivo sensible", ni "cliente con
historial de abuso por encima de un umbral" están implementadas como reglas explícitas
en Rama B — quedan disueltas dentro del criterio libre del LLM ("si tiene más de 5
devoluciones aprobadas en 6 meses, marca como sospechoso", dicho en el prompt, sin
ningún código que lo verifique después).

### 4. HITL: ¿de verdad se puede reanudar un caso?

- **Rama A**: si `refund_amount > 100€`, el Agente 3 no ejecuta nada y devuelve
  `requires_human_approval=True`. Pero no existe ningún código que, una vez que un
  humano apruebe el caso, retome la ejecución (crear la devolución, generar la
  etiqueta, notificar). El panel de Admin/HITL está listado como pendiente en el README
  raíz — hoy ese camino es, en la práctica, un callejón sin salida en código.
- **Rama B**: usa el primitivo `interrupt()` de LangGraph dentro de `resolution_agent`.
  El grafo se **pausa de verdad** en mitad de la ejecución, guarda su estado en el
  checkpointer, y cuando alguien llama con `Command(resume={"approved": True/False})`
  continúa exactamente donde se quedó (incluye tanto el camino de aprobación como el de
  rechazo). Es una implementación de HITL funcionalmente completa, aunque su UI (el
  panel de Admin) tampoco existe todavía en ninguna rama.

### 5. ¿Quién llama a las tools — el LLM o el código?

En Rama A, el LLM decide de forma agéntica cuándo y con qué argumentos llamar a cada
tool (`create_agent(tools=[...])`); el `SYSTEM_PROMPT` le fija un orden, pero es una
convención de prompt, no una garantía de código.

En Rama B, salvo la extracción conversacional del Agente de Triaje, **las tools se
llaman siempre desde Python**, en un orden fijo (`fetch_order_data`, y dentro de
`resolution_agent`: `generate_shipping_label` → `create_return_record` →
`send_customer_notification`), nunca por decisión del LLM. Esto es, en espíritu, la
misma idea que ya aplica Rama A para las *decisiones* de negocio ("el LLM transcribe,
Python decide") pero llevada un paso más allá: en Rama B tampoco decide *qué tool
ejecutar ni en qué orden*.

Consecuencia directa: Rama A tuvo que resolver un bug real de OpenAI (modo "strict" del
JSON Schema rechazando `items: list[dict]` "libre" al combinarlo con `tools` +
`response_format`, ver `README.md`, sección "Correcciones de robustez recientes") y lo
arregló tipando `items`/`products` con Pydantic (`ReturnItem`, `ShippingLabelItem`,
`Product`). Rama B **nunca se topó con ese bug** porque su arquitectura no le da nunca
al LLM la posibilidad de invocar esas tools directamente — no es un fallo suyo, es que
el problema no le aplica por diseño.

### 6. Separación de capas: lógica de negocio vs. transporte MCP

- **Rama A**: `backend/mcp/mcp_supabase.py` y `mcp_logistics.py` contienen la lógica de
  negocio (consultas a Supabase, generación del PDF con `reportlab`) *directamente*
  dentro de las funciones decoradas con `@mcp.tool()`. Si mañana quisiéramos exponer
  "consultar un pedido" desde un endpoint FastAPI sin pasar por MCP, tocaría duplicar
  código o importar un módulo que también sabe hablar el protocolo MCP.
- **Rama B**: introduce `backend/services/supabase_service.py` y
  `logistics_service.py` con la lógica pura (sin nada de MCP), y los servidores MCP
  (`backend/mcp/*.py`) quedan reducidos a *wrappers finos* que solo traducen
  `@mcp.tool()` → llamada a la función del servicio. `defenderAgentes.md` lo razona
  explícitamente como una capa reutilizable tanto por los agentes (vía MCP) como por un
  futuro backend FastAPI (importando `services/` directamente, sin pasar por MCP).

Esto es una aplicación directa del **principio de responsabilidad única** (una función
hace una cosa: o habla SQL, o habla MCP, nunca las dos) y de **inversión de
dependencias** (el backend FastAPI dependerá de `services/`, una abstracción estable,
no de los detalles de cómo se expone por MCP). Es, con diferencia, la mejora de
ingeniería más "gratis" de portar: no cambia ningún comportamiento observable, solo
mueve código de sitio.

### 7. Estado real de los tests

Se comprobó por inspección estática (import de módulos, sin instalar las dependencias
extra de Rama B — `langgraph`, `psycopg-pool`, etc. — que no están en el entorno de
Rama A):

- `tests/integration/test_policy_agent.py`, `test_resolution_agent.py` y
  `test_triage_agent.py` importan `backend.agents.policy_agent`,
  `backend.agents.resolution_agent` y `backend.agents.triage_agent` — módulos que **ya
  no existen**: un commit posterior (`c4cb3a8 "refactor"`) los movió a
  `backend/agents/nodes/{policy,resolution,triage}.py` sin actualizar los tests. Estos 3
  ficheros fallarían con `ModuleNotFoundError` tal cual están hoy.
- `tests/unit/test_routing.py` sí importa el módulo correcto (`backend.agents.graph`),
  pero sus aserciones (`route_after_triage(...) == "triage"` cuando falta información)
  **contradicen el comportamiento actual** del código
  (`route_after_triage` devuelve `"__end__"`, no `"triage"`, desde el commit
  `587890d "fix: route_after_triage devuelve END en vez de loop infinito"`). Ese test
  fallaría también, aunque el import funcione.
- En resumen: **4 de 7 ficheros de test de Rama B no pasarían hoy**, ni por import roto
  ni por aserciones desactualizadas. Es coherente con el nombre de la rama
  (`agentes-tamara-testing`): parece un WIP activo de pruebas, no un estado
  listo para fusionar tal cual.
- Rama A, en cambio, tiene toda su suite en verde (`pytest agente1ConMCP/tests
  agente2ConMCP/tests agente3ConMCP/tests`), incluida la validación cruzada contra el
  dataset sintético.

### 8. Corpus de políticas y dataset de validación

Rama A incluye `dataset/policies/*.md` (16 categorías de producto, cada una con su
propia política de devolución en lenguaje natural — la fuente que se indexa por RAG),
`dataset/generate_dataset.py` (genera pedidos/clientes/devoluciones sintéticos y
etiqueta cada caso con la decisión "correcta") y `dataset/eval_cases.csv` (480 casos
etiquetados). Rama B no tiene nada de esto — probablemente porque, como se explicó en
el resumen ejecutivo, ese trabajo se hizo únicamente en la línea de commits de Rama A
después de la divergencia.

Sin ese corpus, la búsqueda RAG de Rama B (`search_return_policy`) depende
completamente de lo que haya sembrado directamente en la tabla `return_policies` de
Supabase — no hay una fuente versionada en el repositorio ni forma de regenerarla.

### 9. Modelo LLM: configurable vs. fijo

Rama A resuelve el modelo desde una variable de entorno por agente (`AGENTE1_MODEL`,
`AGENTE2_MODEL`, `AGENTE3_MODEL`, todas por defecto `openai:gpt-4o-mini`), lo que
permite cambiarlo sin tocar código (y usar un doble en tests). Rama B fija
`model="gpt-5-nano"` directamente en cada `_build_llm()`, sin variable de entorno,
pero sí varía la `temperature` según el rol del nodo (0.0 para el evaluador — que
busca determinismo —, 0.3–0.4 para los nodos que redactan mensajes empáticos). La idea
de ajustar la temperatura por rol es buena; el hardcodeo del modelo, no tanto.

### 10. Nombres de variables de entorno

Detalle menor pero real: Rama A usa `SUPABASE_URL`, Rama B usa `SUPABASE_API_URL` para
la misma variable de settings (`backend/db/supabase_client.py`). Si se fusionara sin
revisar esto, un `.env` copiado de una rama a otra fallaría en silencio (Pydantic
Settings simplemente no encontraría la variable y lanzaría un error de validación al
arrancar).

### 11. Un defecto que comparten ambas ramas

Ninguna de las dos ramas usa realmente `get_supabase_client()` de
`backend/db/supabase_client.py` para obtener el cliente Supabase: cada `mcp_supabase.py`
(Rama A) / `services/supabase_service.py` (Rama B) reimplementa su propio singleton
perezoso `_client` con `create_async_client(...)`, dejando la función centralizada como
código muerto. Es una pequeña violación de DRY presente en las dos ramas, y se aprovecha
para corregirla en la rama final (ver más abajo).

## Qué se lleva a la rama final, y por qué

| Elemento | Origen | Se adopta | Motivo |
|---|---|---|---|
| Motor de decisión determinista (`_classify_return`, validado contra 480 casos) | Rama A | ✅ Tal cual | Es la pieza más crítica del sistema (decide dinero y plazos) y es la única de las dos versiones que está probada contra un conjunto de casos conocido. Sustituirla por el parseo de JSON en texto libre de Rama B sería un downgrade de fiabilidad, no una mejora. |
| Orquestación con `create_agent` (LangChain 1.x) | Rama A | ✅ Tal cual | Migrar al `StateGraph` de Rama B es un cambio de paradigma completo (nueva forma de invocar los 3 agentes, nuevas dependencias — `langgraph-checkpoint-postgres`, `psycopg-pool` —, y typing preexistente en las 3 tools que Rama B no necesita porque nunca ofrece las tools al LLM). El beneficio (memoria/HITL nativos) no compensa hoy el riesgo de reescribir un sistema que ya funciona y está probado, en una sola fusión. Queda documentado como evolución futura. |
| Dataset sintético + corpus de políticas (`dataset/`) | Rama A | ✅ Tal cual | Es la fuente de verdad del RAG y del dataset de validación; no tiene equivalente en Rama B. |
| Capa `services/` (lógica de negocio separada del transporte MCP) | Rama B | ✅ Portada, adaptada | Mejora de desacoplamiento real y de bajo riesgo: no cambia ningún comportamiento observable ni firma pública, solo mueve la lógica de `mcp_supabase.py`/`mcp_logistics.py` a `services/supabase_service.py`/`logistics_service.py`, dejando los servidores MCP como wrappers finos. Se adapta (no se copia literal) para conservar el tipado Pydantic (`ReturnItem`, `ShippingLabelItem`) que Rama A necesita en la frontera MCP. |
| Cliente Supabase como singleton centralizado | Ninguna (defecto compartido) | ✅ Corregido de nuevo | `backend/db/supabase_client.py::get_supabase_client()` pasa a cachear el cliente y a ser el único punto de creación; `services/supabase_service.py` lo reutiliza en vez de reimplementar su propio `_client`. |
| Memoria conversacional con checkpointer | Rama B | ⏳ No se porta ahora (documentado como siguiente paso) | Requiere el cambio de paradigma de la fila anterior. Se dokumenta explícitamente en el README de la rama final como la mejora más valiosa pendiente, con referencia a `agentes-tamara-testing` como prototipo de referencia. |
| HITL con `interrupt()`/`Command(resume=...)` | Rama B | ⏳ No se porta ahora (documentado como siguiente paso) | Mismo motivo: depende de estar sobre `StateGraph`. Mientras tanto, se mantiene el comportamiento actual de Rama A (`requires_human_approval=True` sin camino de reanudación en código), sin fingir una capacidad que no existe. |
| Modelo LLM configurable por variable de entorno | Rama A | ✅ Tal cual | Más flexible que el modelo fijo de Rama B (permite tests con dobles y cambiar de proveedor sin tocar código). |
| `SUPABASE_URL` como nombre de variable | Rama A | ✅ Tal cual (se descarta `SUPABASE_API_URL`) | Es la que ya está documentada en el README raíz y en `.env.example`; cambiarla no aporta nada y rompería configuraciones existentes. |

### Lo que NO se hace, explícitamente, y por qué

- **No se reescribe el sistema como un único `StateGraph`.** Sería la fusión "ideal" a
  largo plazo (junta lo mejor de las dos: motor determinista de Rama A + memoria/HITL
  reales de Rama B), pero es un cambio de arquitectura de fondo, no algo que se pueda
  hacer "de paso" dentro de esta auditoría sin arriesgar romper lo que hoy funciona. Se
  dejan documentadas ambas piezas (motor determinista y patrón `interrupt()`) para que
  esa migración, cuando se haga, no tenga que redescubrir ninguna de las dos.
- **No se adopta el parseo de JSON en texto libre para la elegibilidad.** Es
  estrictamente peor que lo que ya existe en Rama A en el único punto que de verdad
  importa: la decisión sobre el dinero del cliente.
- **No se arreglan los tests rotos de Rama B dentro de esta rama final.** Pertenecen a
  código (`StateGraph`, checkpointer) que no se está portando todavía; arreglarlos sin
  portar el código que prueban no tendría sentido.

## Cómo verificar la rama final

```bash
pytest agente1ConMCP/tests agente2ConMCP/tests agente3ConMCP/tests -v
python demo_flujo_completo.py   # requiere servidor MCP de Supabase levantado
```

Ver el detalle de los cambios aplicados en el README raíz, sección
"Fusión con `agentes-tamara-testing`", y el historial de commits de la rama
`integracion/mejor-de-ambas-ramas`.
