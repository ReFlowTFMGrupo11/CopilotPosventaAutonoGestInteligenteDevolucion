"""
Ejecuta un Experiment de Langfuse sobre el dataset `policy-eval-golden-set`
(subido antes con migrate_eval_cases_to_langfuse.py).

Reutiliza la misma lógica que tests/qa/scripts/evaluate_rag.py
(_build_state, _build_mock_policy, _result_to_label, _deterministic_label)
para no duplicar el mapeo CSV → estado del agente, pero en vez de escribir
un JSON/MD local, cada caso queda trazado como un run de Langfuse:
pestaña "Experiments" del dataset → verás precisión por caso, comparable entre
ejecuciones (por versión de prompt, de modelo, etc.) en la UI.

Uso:
    python -m tests.qa.scripts.run_langfuse_experiment --dry-run          # gratis, sin LLM
    python -m tests.qa.scripts.run_langfuse_experiment --dry-run --limit 20
    python -m tests.qa.scripts.run_langfuse_experiment --limit 20         # smoke test con LLM real
    python -m tests.qa.scripts.run_langfuse_experiment                   # los 480 casos con LLM real

Requisitos:
    - Haber ejecutado antes migrate_eval_cases_to_langfuse.py
    - LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST en .env
    - OPENAI_API_KEY en .env (solo para el modo real, no en --dry-run)
"""

from __future__ import annotations

import argparse
import logging
from unittest.mock import patch

from dotenv import load_dotenv

load_dotenv(override=True)

from tests.qa.scripts.evaluate_rag import (
    _build_mock_policy,
    _build_state,
    _deterministic_label,
    _result_to_label,
)
from tests.qa.scripts.migrate_eval_cases_to_langfuse import DATASET_NAME

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


def _make_task(dry_run: bool):
    """Construye la función task() que Langfuse ejecuta por cada item del dataset."""

    async def task(*, item, **kwargs) -> str:
        row = item.input  # dict subido por migrate_eval_cases_to_langfuse.py

        if dry_run:
            return _deterministic_label(row)

        from backend.agents.nodes.evaluator import evaluator_agent

        state = _build_state(row)
        allowed_conditions = row["allowed_conditions"].split("|")
        mock_policy = _build_mock_policy(
            row["category"], int(row["max_return_days"]), allowed_conditions
        )

        async def _mock_search(query: str, category: str = "") -> dict:
            return mock_policy

        with patch(
            "backend.agents.nodes.evaluator.search_return_policy",
            side_effect=_mock_search,
        ):
            agent_result = await evaluator_agent(state)
        return _result_to_label(agent_result)

    return task


def label_match_evaluator(*, input, output, expected_output, metadata=None, **kwargs):
    """Evaluator por item: ¿coincide la etiqueta predicha con la esperada?"""
    correct = output == expected_output
    rationale = (metadata or {}).get("rationale", "")
    return {
        "name": "label_match",
        "value": 1.0 if correct else 0.0,
        "comment": (
            f"esperado={expected_output} predicho={output}"
            + (f" | {rationale}" if not correct and rationale else "")
        ),
    }


def accuracy_run_evaluator(*, item_results, **kwargs):
    """Evaluator de run: accuracy agregada sobre todos los items procesados."""
    if not item_results:
        return {"name": "accuracy", "value": 0.0, "comment": "Sin items procesados."}
    hits = sum(
        1
        for r in item_results
        for ev in r.evaluations
        if ev.name == "label_match" and ev.value == 1.0
    )
    total = len(item_results)
    return {
        "name": "accuracy",
        "value": hits / total,
        "comment": f"{hits}/{total} casos correctos.",
    }


def run(limit: int | None, dry_run: bool, run_name: str | None) -> None:
    from langfuse import Langfuse

    lf = Langfuse()
    dataset = lf.get_dataset(DATASET_NAME)
    items = dataset.items[:limit] if limit else dataset.items
    if not items:
        raise SystemExit(
            f"El dataset '{DATASET_NAME}' está vacío. "
            "Ejecuta antes: python -m tests.qa.scripts.migrate_eval_cases_to_langfuse"
        )

    logger.info(
        "Lanzando experimento (%d casos, modo %s)…",
        len(items),
        "dry-run" if dry_run else "LLM real",
    )

    result = lf.run_experiment(
        name="policy-eval" + (" (dry-run)" if dry_run else ""),
        run_name=run_name,
        description="Evaluación de evaluator_agent contra el golden set.",
        data=items,
        task=_make_task(dry_run),
        evaluators=[label_match_evaluator],
        run_evaluators=[accuracy_run_evaluator],
        max_concurrency=5,
        metadata={"mode": "dry-run" if dry_run else "llm"},
    )

    lf.flush()
    logger.info("Experimento completado: %s", result.run_name)
    logger.info(
        "Revisa los resultados en Langfuse: Datasets → %s → Experiments", DATASET_NAME
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Usar solo los primeros N items del dataset.",
    )
    p.add_argument(
        "--dry-run", action="store_true", help="Reglas deterministas, sin LLM (gratis)."
    )
    p.add_argument(
        "--run-name", default=None, help="Nombre exacto para este run (opcional)."
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(limit=args.limit, dry_run=args.dry_run, run_name=args.run_name)
