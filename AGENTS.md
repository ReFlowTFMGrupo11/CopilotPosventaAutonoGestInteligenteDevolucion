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
supabase/        migrations/ (001..013, numbered/sequential), run_all.sql, seed.sql, seed_synthetic.sql.
                 No ER_diagram.md here — see docs/ER_diagram.md (the old supabase/ copy was deleted
                 after it drifted out of sync).
data/            generate_dataset.py (deterministic synthetic data — feeds supabase/seed_synthetic.sql
                 and tests/qa/golden/, both across trees), rag/policies/ (markdown policy docs +
                 ingest_policy_embeddings.py). No qa/ subfolder — the golden eval dataset has zero
                 production consumers, so it lives at tests/qa/golden/ instead (see tests/).
tests/           unit/, integration/, conftest.py (shared fixtures), manual_checks/ (standalone MCP
                 smoke-test scripts, not pytest — see Testing), qa/manual/ (human-run QA kit, 24 curated
                 cases via the Streamlit UI) + qa/golden/ (automated evaluator_agent evaluation against
                 480 synthetic cases, LLM + Langfuse, no UI) — see tests/qa/README.md for the split.
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

`tests/manual_checks/check_mcp_supabase.py` and `check_mcp_logistics.py` are **manual smoke-test
scripts**, not pytest tests — run them directly (`python tests/manual_checks/check_mcp_supabase.py`)
against a live MCP server, not via pytest. They're named `check_*.py` (not `test_*.py`) specifically so
plain `pytest tests/` does not collect and fail on them.

`tests/qa/` is a **separate** QA area with two independent kits — neither runs via plain `pytest tests/`:
`tests/qa/manual/` (24 curated cases, a human clicks through the Streamlit chat UI) and
`tests/qa/golden/` (480 synthetic cases, evaluates `evaluator_agent` with a real/mocked LLM, optionally
via Langfuse). See `tests/qa/README.md` for which one you want and `tests/qa/golden/README.md`
for the Langfuse flow specifically. `tests/qa/golden/scripts/evaluate_evaluator_agent.py --dry-run` does
run automatically in CI (job `qa-golden-dataset-dry-run`) as a regression gate on `policy_rules.py`.

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
Schema reference: `docs/ER_diagram.md` (kept current; the old `supabase/ER_diagram.md` copy was deleted
after it drifted out of sync — it was missing the `thread_id` column from migration 012).

## Gotchas for agents

- CORS in `backend/api/main.py` is wide open (`allow_origins=["*"]`) — this is intentional for local dev,
  not an oversight to "fix" without discussion.
- Per-directory README.md files (`frontend/README.md`, `data/README.md`, `tests/qa/README.md`) contain
  authoritative setup detail for their area — check them before assuming behavior.
