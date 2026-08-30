# AGENTS.md

Guidance for AI coding agents (OpenCode, Claude Code, etc.) working in this repository.

## Project overview

**ReFlow — Copiloto de Posventa Autónomo y Gestión Inteligente de Devoluciones** is a Spanish-language
Master's thesis (TFM) project: a generative-AI multi-agent system that automates e-commerce **returns
management and after-sales support**.

Architecture:
- **LangGraph** — multi-agent orchestration with shared state and persistent (Postgres) memory
- **MCP (Model Context Protocol)** — tool layer connecting agents to Supabase and logistics
- **Supabase (PostgreSQL + pgvector)** — application DB and RAG store for return-policy documents
- **OpenAI models** — reasoning engine
- **FastAPI** backend, **Streamlit** frontend

The core flow is a 3-agent pipeline — **Triage → Policy Evaluator → Resolution** — with Human-in-the-Loop
(HITL) approval required for refunds over `HITL_THRESHOLD_EUR` (default €100). All LangGraph routing is
**100% deterministic**: the LLM never decides which node runs next — deterministic `route_after_*` guard
functions in `backend/agents/graph.py` do.

Code identifiers (functions, classes, variables) are in **English**; docstrings, comments, and user-facing
text are in **Spanish**. Follow this convention when adding code.

## Directory map

```
backend/
  models/        Pydantic domain models (returns.py) + LangGraph state (state.py)
  api/           FastAPI app (main.py), DTOs (schemas.py), routers/ (chat.py, admin.py, orders.py)
  agents/
    graph.py       StateGraph + deterministic route_after_* guard functions + checkpointer
    nodes/          triage.py, evaluator.py, policy_rules.py, resolution.py
    infra/          mcp_client.py (unified MCP client)
  services/      Pure business logic, no MCP/LLM deps — supabase_service.py, logistics_service.py,
                 observability.py (LangFuse)
  mcp/           MCP servers, thin wrappers over services/ — mcp_supabase.py (:8001), mcp_logistics.py (:8002)
  db/            supabase_client.py — cached singleton Supabase client
frontend/        Streamlit app (Chat.py, pages/1_Admin.py, lib/). node_modules/.tanstack are dead
                 leftovers from a removed React prototype — ignore them.
supabase/        migrations/ (001..013, numbered/sequential), run_all.sql, seed.sql, seed_synthetic.sql,
                 ER_diagram.md
data/            generate_dataset.py (deterministic synthetic data), rag/policies/ (markdown policy docs +
                 ingest_policy_embeddings.py), qa/ (eval_cases.csv)
tests/           unit/, integration/, qa/ (separate manual/automated QA kit, not run via plain pytest),
                 conftest.py (shared fixtures), root-level test_mcp_*.py
generated_labels/ Runtime-generated PDFs + notifications_log.jsonl — gitignored, self-regenerating
docs/            architecture.drawio, graph_diagram.md, ER_diagram.md, defensaTFM/ (thesis defense notes)
```

Layering discipline to preserve when editing: `services/` has no MCP/LLM dependency; `mcp/` wraps
`services/`; `agents/nodes/` calls `agents/infra/mcp_client.py`; `agents/graph.py` only wires/routes.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in real credentials
```

Required env vars (see `.env.example`): `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `OPENAI_API_KEY`.
Also needed but **not** in `.env.example` (documentation gap — flag if touching env config):
`SUPABASE_DB_URL` (Postgres connection string, required for the LangGraph checkpointer and demo CLI).
Optional with defaults: `MCP_SUPABASE_URL`, `MCP_LOGISTICS_URL`, `TRIAGE_MODEL`, `EVALUATOR_MODEL`,
`RESOLVER_MODEL`, `HITL_THRESHOLD_EUR`.

Never read or commit `.env` or `.env copy` (both contain live secrets). Note `.env copy` is **not**
covered by `.gitignore`'s `.env.*` patterns — be careful not to stage it.

## Running the app

Manual (4 terminals, must start in this order — each layer depends on the previous):
```bash
python -m backend.mcp.mcp_supabase      # :8001/mcp
python -m backend.mcp.mcp_logistics     # :8002/mcp
uvicorn backend.api.main:app --reload --port 8000   # :8000, Swagger at /docs
streamlit run frontend/Chat.py          # :8501
```

Or use the scripts (macOS/Linux):
```bash
./start_all_mac.sh          # starts all 4 in background, logs to /tmp/reflow_*.log
./start_all_mac.sh stop     # stops everything
```
`start_all.sh` / `start_all_win_gitbash.sh` / `stop_all.sh` are Windows/Git-Bash equivalents.

## Testing

```bash
pytest tests/              # everything
pytest tests/unit/         # unit only
pytest tests/integration/  # integration only
```

Async tests use explicit `@pytest.mark.asyncio` markers (no global `asyncio_mode` set).

`tests/test_mcp_supabase.py` and `tests/test_mcp_logistics.py` are **manual smoke-test scripts**, not
pytest tests, despite the `test_*.py` name — run them directly (`python tests/test_mcp_supabase.py`)
against a live MCP server, not via pytest. Because they live at the root of `tests/`, plain
`pytest tests/` still collects and fails on them (`async def functions are not natively supported`);
CI avoids this by running `pytest tests/unit tests/integration` explicitly instead of `pytest tests/`.

`tests/qa/` is a **separate** manual/automated QA kit (curated CSV/XLSX cases, LangFuse eval scripts,
golden `eval_cases.csv`) — it is not run via plain `pytest tests/`; see `tests/qa/README.md` for its
5-step process, which requires the app running and Supabase seeded.

Test conventions: fixtures named `mock_*`/`sample_*` in `conftest.py`, `unittest.mock.AsyncMock` for
async mocks, test files named `test_<module>.py` mirroring the `services/`/`agents/` module they cover.

## Linting/formatting

No linting or formatting tooling is configured for the Python code (no ruff/black/flake8/mypy config).
Match existing style by hand: snake_case functions/modules, PascalCase classes, `route_after_*` for
LangGraph routing guards, `_has_*` for boolean helper predicates, `Field(default=..., description="...")`
for Pydantic model fields with Spanish descriptions.

Ignore the eslint/prettier/typescript packages sitting in `frontend/node_modules/` — they're leftovers
from a removed React prototype with no active config; the frontend is pure Streamlit (Python) now.

## Database

Supabase/Postgres with pgvector. Migrations are numbered and sequential in `supabase/migrations/`
(`001_create_extensions.sql` ... `013_update_match_policy_embeddings.sql`); apply via `supabase/run_all.sql`.
Seed data via `supabase/seed.sql` / `supabase/seed_synthetic.sql` (generated by `data/generate_dataset.py`).
Schema reference: `docs/ER_diagram.md` (kept current; `supabase/ER_diagram.md` is an older copy —
prefer `docs/ER_diagram.md`).

## Gotchas for agents

- CORS in `backend/api/main.py` is wide open (`allow_origins=["*"]`) — this is intentional for local dev,
  not an oversight to "fix" without discussion.
- Per-directory README.md files (`frontend/README.md`, `data/README.md`, `tests/qa/README.md`) contain
  authoritative setup detail for their area — check them before assuming behavior.
