# Índice de defensa del TFM

Los documentos de esta carpeta responden a dos preguntas distintas que un
tribunal puede hacer, y conviene no mezclarlas en la misma respuesta:

- **"¿Cómo sabéis que el agente decide bien?"** → Pilar 1, observabilidad y
  calidad del comportamiento de IA.
- **"¿Cómo sabéis que el código funciona, y cómo se despliega?"** → Pilar 2,
  infraestructura de ingeniería de software.

---

## Pilar 1 — Observabilidad y calidad del agente

Mide **comportamiento de IA**: si el agente decide bien ante un caso de
negocio. No mide corrección de código.

| Documento | Qué responde |
|---|---|
| [`defenderLangfuse.md`](defenderLangfuse.md) | Trazabilidad en tiempo real de cada llamada al LLM (prompt, contexto RAG, tokens, latencia) — para depurar un caso concreto que salió mal |
| [`defenderDashboardCostes.md`](defenderDashboardCostes.md) | Por qué existe un dashboard propio de coste/latencia **además de** Langfuse, no en su lugar |
| [`defenderDatos.md`](defenderDatos.md) | El golden dataset (480 casos, etiquetas calculadas sin IA) — evaluación automática masiva de si `evaluator_agent` clasifica bien |
| [`defenderRAG.md`](defenderRAG.md) | Calidad de la búsqueda semántica de políticas — incluye la investigación real de por qué el umbral 0.7 dejaba el RAG sin devolver nada, y la optimización de coste que salta el RAG cuando el veto ya es determinista |
| [`../../evaluation/README.md`](../../evaluation/README.md) | Los dos kits de QA: 480 casos automáticos (`golden/`) vs 24 casos curados a mano (`manual/`) |

**Las tres capas de garantía de calidad del agente, de más a menos automatizado:**
1. **Langfuse** — trazas en vivo, para depurar un caso puntual ya ocurrido.
2. **Golden dataset (480 casos)** — evaluación automática masiva, sin LLM-as-judge (las etiquetas salen de reglas Python, no de otro modelo).
3. **QA manual (24 casos)** — revisión humana curada, end-to-end contra la app real.

Ninguna sustituye a las otras dos: Langfuse no agrega ("¿cuántos casos aprobamos mal el mes pasado?"), el golden dataset no prueba la app real (mockea el RAG), y el QA manual no escala a cientos de casos.

## Pilar 2 — Infraestructura de ingeniería de software

Mide **corrección de código**: si una función/endpoint hace lo que dice. No
juzga si una decisión de negocio del agente es acertada.

| Documento | Qué responde |
|---|---|
| [`defenderTesting.md`](defenderTesting.md) | Las 3 capas de test de código (`unit/`, `integration/`, `manual_checks/`), por qué esa frontera, y el estado real de CD |
| [`defenderCI.md`](defenderCI.md) | Los 9 jobs del pipeline de CI — qué bloquea el merge y qué no |
| [`defenderFastAPI.md`](defenderFastAPI.md) | Por qué FastAPI y no Flask/Django para el backend |
| [`defenderMCP.md`](defenderMCP.md) | Arquitectura de los servidores MCP (Supabase/Logística) |
| [`defenderConcurrencia.md`](defenderConcurrencia.md) | Protección frente a peticiones simultáneas sobre el mismo `thread_id` |
| [`defenderAgentes.md`](defenderAgentes.md) | Por qué LangGraph y no una cadena LangChain simple para el grafo de 3 agentes |

**Nota sobre CD**: en desarrollo activo (PR #47), no fusionada a `main`, sin
decisión de arquitectura estable todavía que defender — ver
[`defenderTesting.md`](defenderTesting.md) §5 para la respuesta honesta si
se pregunta en la defensa.

## El único punto donde ambos pilares se tocan

El job `qa-golden-dataset-dry-run` de CI ejecuta
`evaluate_evaluator_agent.py --dry-run` — pero en ese modo no evalúa al LLM,
comprueba que las reglas deterministas del generador del dataset
(`classify_case()`) siguen siendo consistentes con `policy_rules.py`. Ese job
concreto es Pilar 2 (consistencia de código), aunque reutilice el mismo
dataset que, ejecutado sin `--dry-run`, sí es una herramienta de Pilar 1
(evaluación del agente). Es la única costura entre ambos — el resto de cada
pilar es independiente del otro.
