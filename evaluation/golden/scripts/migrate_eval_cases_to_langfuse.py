"""
Sube el golden dataset (evaluation/golden/eval_cases.csv) a Langfuse como Dataset.

Crea (o reutiliza) el dataset `policy-eval-golden-set` en la instancia de
Langfuse configurada por LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY/LANGFUSE_HOST
(.env de la raíz) y sube cada fila del CSV como un dataset item:

  - input:           las columnas que necesita evaluator_agent
                      (mismo shape que usa evaluate_evaluator_agent.py::_build_state)
  - expected_output:  la columna `expected_label` (valid/invalid/human_review)
  - metadata:         case_id, category y rationale, para poder leer el
                      "por qué" de cada caso directamente en la UI de Langfuse

Idempotente: si el dataset ya tiene items con esos `case_id` en metadata,
se saltan (usa --force para subir duplicados igualmente).

Uso:
    python -m evaluation.golden.scripts.migrate_eval_cases_to_langfuse
    python -m evaluation.golden.scripts.migrate_eval_cases_to_langfuse --limit 10   # smoke test
    python -m evaluation.golden.scripts.migrate_eval_cases_to_langfuse --force

Requisitos:
    LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY en .env (ya están si el
    tracing de backend/services/observability.py funciona; se usa el mismo
    proyecto de Langfuse Cloud)
"""

from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

# parents[3]: scripts/ -> golden/ -> evaluation/ -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
EVAL_CSV = REPO_ROOT / "evaluation" / "golden" / "eval_cases.csv"
DATASET_NAME = "policy-eval-golden-set"

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


def _load_rows(csv_path: Path, limit: int | None) -> list[dict]:
    """Lee las filas del CSV de casos golden, limitando opcionalmente a las primeras N."""
    with csv_path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return rows[:limit] if limit else rows


def _existing_case_ids(dataset) -> set[str]:
    """Devuelve el conjunto de ``case_id`` ya presentes en la metadata de los items del dataset."""
    return {
        item.metadata["case_id"]
        for item in dataset.items
        if item.metadata and item.metadata.get("case_id")
    }


def migrate(limit: int | None = None, force: bool = False) -> None:
    """Sube los casos del golden dataset como items del dataset de Langfuse.

    Crea (o reutiliza) el dataset ``policy-eval-golden-set`` y, por cada fila
    del CSV, crea un dataset item con las columnas necesarias para reconstruir
    el estado del agente (``input``), la etiqueta esperada (``expected_output``)
    y metadatos de trazabilidad (``metadata``). Es idempotente: salta los
    ``case_id`` que ya existen en el dataset, salvo que se indique ``force=True``.

    Args:
        limit: Si se indica, sube solo los primeros N casos del CSV.
        force: Si es True, sube también los casos cuyo ``case_id`` ya exista en el dataset.
    """
    from langfuse import Langfuse

    lf = Langfuse()
    lf.create_dataset(
        name=DATASET_NAME,
        description="480 casos golden para validar evaluator_agent "
        "(fuente: evaluation/golden/eval_cases.csv).",
        metadata={"source": "evaluation/golden/eval_cases.csv"},
    )

    dataset = lf.get_dataset(DATASET_NAME)
    already = set() if force else _existing_case_ids(dataset)
    if already:
        logger.info("%d items ya existen en el dataset, se omiten.", len(already))
    rows = _load_rows(EVAL_CSV, limit)
    created = 0
    for row in rows:
        case_id = row["case_id"]
        if case_id in already:
            continue

        lf.create_dataset_item(
            dataset_name=DATASET_NAME,
            input={
                "case_id": case_id,
                "order_number": row["order_number"],
                "customer_email": row["customer_email"],
                "category": row["category"],
                "reason_category": row["reason_category"],
                "condition": row["condition"],
                "max_return_days": row["max_return_days"],
                "allowed_conditions": row["allowed_conditions"],
                "days_since_delivery": row["days_since_delivery"],
                "refund_amount": row["refund_amount"],
                "is_frequent_returner": row["is_frequent_returner"],
            },
            expected_output=row["expected_label"],
            metadata={
                "case_id": case_id,
                "category": row["category"],
                "rationale": row["rationale"],
            },
        )
        created += 1

    lf.flush()
    logger.info(
        "Listo: %d items nuevos subidos a '%s' (%d ya existían, %d en total en el CSV).",
        created,
        DATASET_NAME,
        len(already),
        len(rows),
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--limit", type=int, default=None, help="Subir solo los primeros N casos."
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Subir aunque ya existan items con ese case_id.",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    migrate(limit=args.limit, force=args.force)
