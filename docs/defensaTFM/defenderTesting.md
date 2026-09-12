# Defender la pirámide de tests y su conexión con CI/CD

Este documento recoge los argumentos para defender, en la memoria/presentación del
TFM, **la infraestructura de tests de código** de ReFlow: por qué hay tres capas
distintas (`tests/unit/`, `tests/integration/`, `tests/manual_checks/`), qué
verifica cada una, cómo se conectan con el pipeline de CI (`.github/workflows/ci.yml`,
ver [`defenderCI.md`](defenderCI.md)), y el estado real de CD.

**Alcance deliberadamente distinto del de la observabilidad del agente**: este
documento habla de si **el código** funciona (¿un endpoint devuelve lo que debe?,
¿una función calcula bien?). Si buscas si **el agente decide bien** (Langfuse,
golden dataset de 480 casos, QA manual de 24 casos), ve a
[`defenderLangfuse.md`](defenderLangfuse.md) y [`defenderDatos.md`](defenderDatos.md)
— son medidas de calidad de comportamiento de IA, no de corrección de código, aunque
ambas familias vivan bajo `tests/`. Ver el índice en `docs/defensaTFM/README.md`
para el mapa completo.

---

## 1. Tres capas, no una — qué verifica cada una

| | `tests/unit/` | `tests/integration/` | `tests/manual_checks/` |
|---|---|---|---|
| **Qué prueba** | Una función/endpoint aislado | El grafo LangGraph completo, con nodos reales encadenados | Que un servidor MCP real responde |
| **Qué mockea** | Todo lo externo (Supabase, LLM, grafo) | El LLM (`_build_llm` mockeado) y los tools MCP; el grafo y el routing son **reales** | Nada — servidor levantado de verdad |
| **Velocidad** | Milisegundos | Milisegundos (sin red real) | Segundos (red real) |
| **Se ejecuta con `pytest`** | Sí | Sí | **No** — scripts standalone (`check_*.py`, no `test_*.py`, para que `pytest` no los recoja) |
| **Corre en CI** | Sí, cada PR (`ci.yml::test`) | Sí, cada PR (mismo job) | No — necesitaría los 2 servers MCP levantados en el runner |
| **Ejemplo real de hoy** | `test_pricing.py` — aritmética de coste, cero I/O | `test_graph_flow.py` — turno completo triage→evaluator→resolver | `check_mcp_supabase.py` — ¿responde `get_order_details` de verdad? |

### Por qué esta frontera concreta, no otra

- **`unit/` mockea TODO, incluso lo que `integration/` no mockea (el grafo)**: la
  pregunta que responde `unit/` es *"¿esta pieza aislada hace lo que dice, dado
  cualquier input?"* — meter el grafo real ahí solo añadiría acoplamiento sin
  aportar nada a esa pregunta.
- **`integration/` mockea el LLM pero no el grafo**: la pregunta que responde es
  *"¿el routing entre nodos (`route_after_triage`, `route_after_evaluator`...) hace
  lo correcto dado lo que el LLM devolvió?"* — necesita el grafo real para que esa
  pregunta tenga sentido, pero no necesita gastar tokens reales para responderla
  (el LLM se mockea con una respuesta fija).
- **`manual_checks/` no es pytest a propósito**: nombrado `check_*.py` (no
  `test_*.py`) para que ni `pytest tests/` ni CI lo recojan por accidente — exige
  los 2 servers MCP levantados a mano, algo que no tiene sentido automatizar en
  cada PR (ver §4 de [`defenderCI.md`](defenderCI.md), mismo argumento de
  infraestructura real vs mockeada).

---

## 2. Caso real: la auditoría de hoy — de 105 a 209 tests

Al revisar la estructura de `tests/unit/`, se encontraron **6 módulos con lógica
real y cero test dedicado**: `pricing.py`, `usage_service.py`, `mcp_client.py`,
`llm_factory.py`, `usage_tracking.py`, `observability.py` (409 líneas, el más
grande). Además, una fixture muerta (`mock_supabase_client`, sin ningún
consumidor en todo el repo).

### El hallazgo más interesante: un fixture autouse bloqueaba su propia cobertura

`tests/conftest.py` tiene un fixture `autouse=True` (`_no_real_langfuse`) que
parchea `observability.get_langfuse()` a `None` en **toda** la suite, para no
llamar a Langfuse de verdad durante los tests. Efecto secundario no buscado:
**ninguna rama `if lf:` de `observability.py` se ejecutaba nunca**, porque ese
fixture parchea exactamente la función que había que probar.

Solución: un fixture con el **mismo nombre** (`_no_real_langfuse`) definido
dentro de `test_observability.py` — en pytest, un fixture del propio módulo de
test tiene prioridad sobre uno homónimo de un `conftest.py` más alto en el
árbol. Con eso, solo ese fichero recupera el comportamiento real de
`get_langfuse()`, sin tocar el comportamiento del resto de la suite.

### Hallazgo colateral, sin relación con testing en sí

Escribir los tests de `llm_factory.py` destapó que **`gpt-5-mini` (familia
"reasoning") ignora silenciosamente el parámetro `temperature` en
`ChatOpenAI`** — confirmado comparando con `gpt-4o-mini`, que sí lo respeta.
Afecta a `evaluator.py`, que pasa `temperature=0.0` con el comentario
*"determinista para auditoría"*: ese argumento no tiene ningún efecto real con
el modelo actual. No se corrigió (fuera de alcance de un test), solo se
documentó — ejemplo de cómo escribir tests de infraestructura destapa bugs de
negocio que ninguna revisión de código a ojo habría encontrado.

### Proporción, no sobre-ingeniería

| | Líneas |
|---|---|
| `backend/` (código de producción) | 5.598 |
| `tests/unit/` + `tests/integration/` | 3.980 |

Ratio ~0.71:1 — dentro del rango normal de un proyecto que se toma el testing en
serio, no un caso de exceso. La pregunta relevante en una defensa no es *"¿son
demasiados tests?"* sino *"¿cada test aporta una pregunta real que responder?"*
— cada uno de los 104 tests nuevos cierra un módulo que antes tenía exactamente
cero cobertura, no repite lo que otro test ya cubría.

---

## 3. La correspondencia 1:1 entre routers, tests y páginas del frontend

Antes de la auditoría, `test_api_endpoints.py` cubría los 3 routers backend
(`chat.py`/`admin.py`/`orders.py`) a la vez, en un solo fichero de 410 líneas —
mismo problema que tenían los propios routers, donde `admin.py` servía dos
páginas de frontend distintas (`1_Admin.py` y `2_Costes.py`) mientras que
`orders.py` (con `/api/stats` y la búsqueda de pedido) solo lo consumía una de
ellas, nunca el chat de cliente.

Se resolvió en dos pasos coordinados:
1. **Reorganizar los routers** para que cada uno corresponda a una sola página:
   `orders.py` se elimina, sus 2 endpoints de uso exclusivo del panel pasan a
   `admin.py` (nuevo `public_router` en el mismo fichero, mismas URLs); los
   endpoints de coste se extraen a un `usage.py` nuevo.
2. **Dividir los tests siguiendo la misma frontera**: `test_main.py`
   (`/health`), `test_chat.py`, `test_admin.py`, `test_usage.py` — con un
   `tests/unit/conftest.py` nuevo para los fixtures compartidos entre los 4.

Resultado: `chat.py` ↔ `Chat.py`, `admin.py` ↔ `1_Admin.py`, `usage.py` ↔
`2_Costes.py` — tanto en el código de producción como en sus tests. Verificado
con `app.openapi()` que las URLs HTTP no cambiaron (mismas 16 rutas) — la
reorganización es puramente de "en qué fichero vive cada cosa", no del
contrato con el frontend.

---

## 4. Conexión con CI — qué de esto corre en cada PR

El job `test` de `.github/workflows/ci.yml` ejecuta literalmente
`pytest tests/unit tests/integration -v` — los 209 tests (unit+integration) se
ejecutan en **cada PR**, sin necesidad de tocar el workflow cuando se añaden
tests nuevos (confirmado: los 104 tests de esta auditoría ya corren en CI sin
ningún cambio a `ci.yml`). `manual_checks/` **no** corre en CI — necesitaría los
2 servidores MCP levantados en el runner, algo que el job `smoke-boot` sí hace
pero para un propósito distinto (arrancar los procesos, no probar su lógica de
negocio — ver [`defenderCI.md`](defenderCI.md) §4).

---

## 5. Estado de CD — honesto: en desarrollo, no listo para defender

Existe una rama (`feature/despliegue-aws-ecs-fargate`, PR #47) con Docker
Compose + despliegue en AWS ECS Fargate para los 4 servicios — **explícitamente
marcada "TESTING - NO MERGE"** por quien la abrió. No está en `main` y, a fecha
de escribir esto, está desactualizada respecto a `main` (se creó antes de que
se mergeara la visibilidad del checkpointer degradado, entre otros cambios) —
fusionarla tal cual perdería esa función sin querer. Es trabajo real y en
curso, pero no hay todavía una decisión de arquitectura estable que defender
aquí; cuando la rama se actualice contra `main` y se decida su diseño final,
esta sección se amplía. Mientras tanto, la respuesta honesta a *"¿y el
despliegue?"* en la defensa es: *"CI cubre validación de PRs; CD está en
desarrollo activo, no en `main` todavía"* — no *"no existe"* ni fingir que ya
está resuelto.

---

## 6. Preguntas frecuentes de la defensa

**¿Por qué no hay un solo tipo de test, más simple?**
Cada capa responde una pregunta que las otras no pueden: `unit/` aísla la
lógica de una pieza, `integration/` prueba que las piezas encajan sin gastar en
LLM real, `manual_checks/` prueba que la infraestructura de red (servers MCP)
funciona de verdad. Ninguna sustituye a las otras dos.

**¿Por qué `manual_checks/` no está automatizado en CI, si ya existe?**
Porque requiere los 2 servidores MCP corriendo — sí sería automatizable (con
`services:` de GitHub Actions, como se plantea para un hipotético test
end-to-end con Postgres real en [`defenderCI.md`](defenderCI.md) §5), pero el
beneficio marginal (detectar que un server MCP concreto no arranca) ya lo cubre
`smoke-boot` de una forma más barata, sin necesitar que ambos MCP servers
hablen entre sí.

**¿No es un poco tarde en el proyecto para escribir 104 tests nuevos?**
Es una pregunta legítima de gestión de tiempo, no de calidad técnica: el ratio
código:test (0.71:1) no es excesivo, y cada test cierra un hueco real, no
repite cobertura. Pero cerrar *cada* hueco restante desde este punto tiene
retorno decreciente para una defensa concreta — el argumento de rigor ya está
hecho con estos 104; perseguir el 100% de las ramas de `observability.py` no
añade mucho más peso argumental.
