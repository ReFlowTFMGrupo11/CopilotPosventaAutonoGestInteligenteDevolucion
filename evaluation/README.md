# 🧪 QA — ReFlow Chatbot de Devoluciones

Este directorio agrupa **dos kits de QA completamente independientes**, que no
comparten datos ni herramientas — no hace falta correr uno para usar el otro:

| | [`manual/`](manual/README.md) | [`golden/`](golden/README.md) |
|---|---|---|
| **Qué es** | 24 casos curados a mano, para un humano | 480 casos sintéticos, para un script |
| **Cómo se ejecuta** | Escribiendo mensajes en el chat de Streamlit (UI) | `python -m evaluation.golden.scripts...` (sin UI) |
| **Quién lo corre** | Una persona, siguiendo una guía de 5 pasos | El agente evaluador real (LLM) o reglas deterministas |
| **Qué mide** | "¿Responde bien el chatbot completo, de punta a punta?" | "¿Clasifica bien `evaluator_agent` valid/invalid/human_review?" |
| **¿Toca RAG de verdad?** | Sí (vía la app real) | El evaluador golden habitual no (mockea RAG); `golden/scripts/evaluate_live_rag.py --live` sí consulta el índice real |
| **¿Corre en CI?** | No, nunca (requiere un humano) | Sí, `--dry-run` en cada push (ver `.github/workflows/ci.yml`) |

Si buscas "cómo prueba manualmente el chatbot" → [`manual/README.md`](manual/README.md).
Si buscas "cómo se mide la accuracy del agente / cómo se sube a Langfuse" o la evaluación opcional del RAG real → [`golden/README.md`](golden/README.md).

`results/` (dentro de `golden/`, gitignored) son los informes locales que genera
`evaluate_evaluator_agent.py` — no se comitean, se regeneran en cada ejecución.
