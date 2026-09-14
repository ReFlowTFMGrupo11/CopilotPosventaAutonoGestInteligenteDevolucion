"""
Ejecuta un Experiment de Langfuse sobre el dataset `policy-eval-golden-set`
(subido antes con migrate_eval_cases_to_langfuse.py).

Reutiliza la misma lógica que evaluation/golden/scripts/evaluate_evaluator_agent.py
(_build_state, _build_mock_policy, _result_to_label, _deterministic_label)
para no duplicar el mapeo CSV → estado del agente, pero en vez de escribir
un JSON/MD local, cada caso queda trazado como un run de Langfuse:
pestaña "Experiments" del dataset → verás precisión por caso, comparable
entre ejecuciones. En modo LLM real, el run queda etiquetado con
`metadata.prompt_version` = la versión `production` de `policy-system-prompt`
en Langfuse (subida por scripts/sync_prompts_to_langfuse.py) si coincide con
el código que de verdad se ejecutó -- si no coincide (prompt editado sin
sincronizar todavía), se avisa por log y el run queda sin esa metadata, para
no comparar accuracy contra una versión de prompt que no es la real.

Uso:
    python -m evaluation.golden.scripts.run_langfuse_experiment --dry-run          # gratis, sin LLM
    python -m evaluation.golden.scripts.run_langfuse_experiment --dry-run --limit 20
    python -m evaluation.golden.scripts.run_langfuse_experiment --limit 20         # smoke test con LLM real
    python -m evaluation.golden.scripts.run_langfuse_experiment                   # los 480 casos con LLM real

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

from evaluation.golden.scripts.evaluate_evaluator_agent import (
    _build_mock_policy,
    _build_state,
    _deterministic_label,
    _result_to_label,
)
from evaluation.golden.scripts.migrate_eval_cases_to_langfuse import DATASET_NAME
from scripts.sync_prompts_to_langfuse import get_production_prompt

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


def _make_task(dry_run: bool):
    """Construye la función task() que Langfuse ejecuta por cada item del dataset."""

    async def task(*, item, **kwargs) -> str:
        """Evalúa un item del dataset (LLM real o reglas deterministas) y devuelve la etiqueta predicha."""
        row = item.input  # dict subido por migrate_eval_cases_to_langfuse.py

        if dry_run:
            return _deterministic_label(row)

        from backend.agents.nodes.evaluator import evaluator_agent

        state = _build_state(row)
        allowed_conditions = row["allowed_conditions"].split("|")
        mock_policy = _build_mock_policy(
            row["category"], int(row["max_return_days"]), allowed_conditions
        )

        async def _mock_search(
            query: str, category: str = "", thread_id: str = ""
        ) -> dict:
            """Sustituye a search_return_policy() devolviendo la policy mockeada de este item."""
            return mock_policy

        async def _mock_policy_info(category: str) -> dict:
            """Sustituye a get_policy_info() (pre-check determinista, ver evaluator.py)."""
            return mock_policy.get("policy_info") or {}

        with patch(
            "backend.agents.nodes.evaluator.get_policy_info",
            side_effect=_mock_policy_info,
        ), patch(
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
    """Lanza un Experiment de Langfuse contra el dataset `policy-eval-golden-set`.

    Recupera el dataset ya subido por ``migrate_eval_cases_to_langfuse.py`` y,
    para cada item, ejecuta la tarea de evaluación (LLM real o reglas
    deterministas en ``dry_run``), comparando la etiqueta predicha con la
    esperada mediante ``label_match_evaluator`` y agregando la accuracy del
    run con ``accuracy_run_evaluator``. El resultado queda registrado como un
    Dataset Run visible en la UI de Langfuse.

    Args:
        limit: Si se indica, usa solo los primeros N items del dataset.
        dry_run: Si es True, usa las reglas deterministas en vez del LLM real.
        run_name: Nombre opcional para identificar este run en Langfuse.
    """
    from langfuse import Langfuse

    lf = Langfuse()
    dataset = lf.get_dataset(DATASET_NAME)
    items = dataset.items[:limit] if limit else dataset.items
    if not items:
        raise SystemExit(
            f"El dataset '{DATASET_NAME}' está vacío. "
            "Ejecuta antes: python -m evaluation.golden.scripts.migrate_eval_cases_to_langfuse"
        )

    logger.info(
        "Lanzando experimento (%d casos, modo %s)…",
        len(items),
        "dry-run" if dry_run else "LLM real",
    )

    # Prompt activo: solo aplica en modo LLM real (--dry-run no llama a
    # evaluator_agent) -- ver docstring del módulo.
    metadata: dict[str, str] = {"mode": "dry-run" if dry_run else "llm"}
    if not dry_run:
        from backend.agents.nodes.evaluator import POLICY_SYSTEM_PROMPT

        candidate = get_production_prompt(lf, "policy-system-prompt")
        if candidate is None:
            logger.warning(
                "policy-system-prompt no existe todavía en Langfuse -- este "
                "run no llevará prompt_version. Corre "
                "`python -m scripts.sync_prompts_to_langfuse` antes de evaluar."
            )
        elif candidate.prompt != POLICY_SYSTEM_PROMPT:
            logger.warning(
                "POLICY_SYSTEM_PROMPT (código) difiere de la versión "
                "'production' v%d en Langfuse -- este run no llevará "
                "prompt_version (evita comparar accuracy contra una versión "
                "que no es la que de verdad se ejecutó). Corre "
                "`python -m scripts.sync_prompts_to_langfuse` antes de evaluar "
                "si quieres que quede etiquetado.",
                candidate.version,
            )
        else:
            metadata["prompt_version"] = str(candidate.version)
            logger.info(
                "Experimento etiquetado con policy-system-prompt v%d",
                candidate.version,
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
        metadata=metadata,
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
