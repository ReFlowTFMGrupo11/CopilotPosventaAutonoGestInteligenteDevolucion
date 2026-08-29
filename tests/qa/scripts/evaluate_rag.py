"""
Evaluador end-to-end del pipeline RAG + Agente Evaluador de Políticas.

Lee los 480 casos de data/qa/eval_cases.csv, construye un estado mínimo
por caso, mockea el RAG con los chunks REALES del corpus (sin llamadas
a OpenAI ni a Supabase) y ejecuta evaluator_agent con el LLM real
(gpt-5-mini). Calcula precisión, recall y F1 por clase y por categoría,
y vuelca el informe como JSON y tabla Markdown en:

  tests/qa/results/eval_report_<timestamp>.json
  tests/qa/results/eval_report_<timestamp>.md

Uso:
    python -m tests.qa.scripts.evaluate_rag                  # todos los casos
    python -m tests.qa.scripts.evaluate_rag --limit 50       # primeros N casos
    python -m tests.qa.scripts.evaluate_rag --category calzado
    python -m tests.qa.scripts.evaluate_rag --dry-run        # lógica determinista, sin LLM

Modo --dry-run: en vez de llamar al LLM, aplica las reglas deterministas
directamente sobre las columnas del CSV (plazo, importe HITL, is_frequent_returner)
para validar que el golden dataset es internamente consistente.  Ideal para CI.

Requisitos (solo para el modo real):
    OPENAI_API_KEY en .env
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from dotenv import load_dotenv

load_dotenv(override=True)

# ── Rutas ──────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[3]
EVAL_CSV = REPO_ROOT / "data" / "qa" / "eval_cases.csv"
POLICIES_DIR = REPO_ROOT / "data" / "rag" / "policies"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"

# ── Umbrales deterministas (deben coincidir con la lógica del agente) ──────
HITL_AMOUNT_THRESHOLD = 100.0  # €  → human_review
HITL_FREQUENT_RETURNER = True  # is_frequent_returner=True → human_review
BORDER_ZONE_DAYS = 5  # plazo ± 5 días → human_review (zona frontera)

LABELS = ["valid", "invalid", "human_review"]

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────


def _load_cases(csv_path: Path, limit: int | None, category: str | None) -> list[dict]:
    with csv_path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if category:
        rows = [r for r in rows if r["category"] == category]
    if limit:
        rows = rows[:limit]
    return rows


def _build_mock_policy(
    category: str, max_return_days: int, allowed_conditions: list[str]
) -> dict:
    """Construye un objeto policy_info mínimo a partir de las columnas del CSV
    (sin necesidad de BD). Incluye los chunks RAG del corpus real.

    ``allowed_conditions`` viene de la columna homónima de eval_cases.csv
    (la real, específica de la categoría de este caso) — antes de este fix
    se usaba una lista fija igual para las 16 categorías, sin relación con
    la que usó classify_case() para calcular expected_label.
    """
    policy_doc_map = {
        "electronica_informatica": "01_electronica_informatica.md",
        "electrodomesticos": "02_electrodomesticos.md",
        "moda_ropa": "03_moda_ropa.md",
        "calzado": "04_calzado.md",
        "joyeria_relojes": "05_joyeria_relojeria.md",
        "hogar_decoracion": "06_hogar_decoracion.md",
        "muebles": "07_muebles.md",
        "jardineria_bricolaje": "08_jardineria_bricolaje.md",
        "juguetes": "09_juguetes.md",
        "bebe_puericultura": "10_bebe_puericultura.md",
        "deportes_aire_libre": "11_deportes_aire_libre.md",
        "cosmetica_perfumeria": "12_cosmetica_perfumeria.md",
        "drogueria_salud": "13_drogueria_salud.md",
        "alimentacion": "14_alimentacion.md",
        "mascotas": "15_mascotas.md",
        "libros_papeleria": "16_libros_papeleria.md",
    }
    doc = policy_doc_map.get(category)
    policy_text = (POLICIES_DIR / doc).read_text(encoding="utf-8") if doc else ""
    general_text = (POLICIES_DIR / "00_marco_general_devoluciones.md").read_text(
        encoding="utf-8"
    )

    return {
        "query": f"devolución {category}",
        "category": category,
        "semantic_results": [
            {"chunk_text": policy_text[:2000], "similarity": 0.92},
            {"chunk_text": general_text[:2000], "similarity": 0.85},
        ],
        "policy_info": {
            "category": category,
            "max_return_days": max_return_days,
            "requires_original_packaging": False,
            "restocking_fee_percent": 0.0,
            "allowed_conditions": allowed_conditions,
            "policy_text": policy_text,
            "active": True,
        },
    }


def _build_state(row: dict) -> dict[str, Any]:
    """Construye el estado mínimo que necesita evaluator_agent."""
    order_item_id = f"oi-eval-{row['case_id'][:8]}"
    # delivered_at simulado: ahora - days_since_delivery
    days = int(row["days_since_delivery"])
    now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
    from datetime import timedelta

    delivered = now - timedelta(days=days)

    return {
        "messages": [],
        "order_details": {
            "order": {
                "id": f"ord-eval-{row['case_id'][:8]}",
                "order_number": row["order_number"],
                "status": "delivered",
                "delivered_at": delivered.isoformat(),
                "created_at": delivered.isoformat(),
                "customer": {
                    "id": f"cust-eval-{row['case_id'][:8]}",
                    "email": row["customer_email"],
                    "full_name": "Cliente Eval",
                },
            },
            "items": [
                {
                    "id": order_item_id,
                    "order_id": f"ord-eval-{row['case_id'][:8]}",
                    "quantity": 1,
                    "unit_price": float(row["refund_amount"]),
                    "total_price": float(row["refund_amount"]),
                    "product": {
                        "name": f"Producto {row['category']}",
                        "sku": f"SKU-EVAL-{row['case_id'][:6]}",
                        "category": row["category"],
                        "price": float(row["refund_amount"]),
                        "weight_kg": 0.5,
                    },
                }
            ],
        },
        "return_history": {
            "customer_id": f"cust-eval-{row['case_id'][:8]}",
            "total_returns": 7 if row["is_frequent_returner"] == "True" else 0,
            "approved": 6 if row["is_frequent_returner"] == "True" else 0,
            "rejected": 0,
            "returns": [],
        },
        "reason": f"Motivo de evaluación: {row['reason_category']}",
        "reason_category": row["reason_category"],
        "items_to_return": [
            {
                "order_item_id": order_item_id,
                "quantity": 1,
                # Columna real de eval_cases.csv (la que classify_case() usó
                # para calcular expected_label) — antes de este fix se
                # ADIVINABA con una regla de 2 valores sin relación con el
                # caso real, porque el CSV no la exportaba.
                "condition": row["condition"],
            }
        ],
    }


def _deterministic_label(row: dict) -> str:
    """Reproduce la lógica determinista del agente sin LLM.
    Útil para --dry-run y para validar el golden dataset.
    """
    days = int(row["days_since_delivery"])
    max_days = int(row["max_return_days"])
    amount = float(row["refund_amount"])
    frequent = row["is_frequent_returner"] == "True"

    # Fuera de plazo (con margen de 5 días para zona frontera)
    if days > max_days + BORDER_ZONE_DAYS:
        return "invalid"
    # Zona frontera del plazo
    if max_days - BORDER_ZONE_DAYS < days <= max_days + BORDER_ZONE_DAYS:
        return "human_review"
    # HITL por importe
    if amount > HITL_AMOUNT_THRESHOLD:
        return "human_review"
    # HITL por cliente frecuente
    if frequent:
        return "human_review"
    return "valid"


def _result_to_label(result: dict[str, Any]) -> str:
    """Convierte la salida de evaluator_agent en una etiqueta comparable."""
    any_eligible = result.get("any_eligible", False)
    items = result.get("items_eligibility", [])

    # Si el agente marcó HITL (ningún artículo elegible pero no rechazado explícitamente)
    # la heurística es: si el refund_amount > umbral → human_review
    if not items:
        return "invalid"

    # Tomamos el primer item (casos single-item del CSV)
    item = items[0]
    if not item.get("is_eligible"):
        return "invalid"

    # is_eligible=True pero importe > umbral → human_review (HITL)
    if item.get("refund_amount", 0) > HITL_AMOUNT_THRESHOLD:
        return "human_review"

    return "valid"


# ── Métricas ───────────────────────────────────────────────────────────────


def _compute_metrics(results: list[dict]) -> dict:
    """Calcula accuracy, precision, recall y F1 por clase y macro-average."""
    from collections import Counter

    per_class: dict[str, dict] = {lbl: {"tp": 0, "fp": 0, "fn": 0} for lbl in LABELS}
    correct = 0

    for r in results:
        exp = r["expected"]
        pred = r["predicted"]
        if exp == pred:
            correct += 1
            per_class[exp]["tp"] += 1
        else:
            per_class[pred]["fp"] += 1
            per_class[exp]["fn"] += 1

    total = len(results)
    accuracy = correct / total if total else 0.0

    class_metrics: dict[str, dict] = {}
    for lbl, counts in per_class.items():
        tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            (2 * precision * recall / (precision + recall))
            if (precision + recall) > 0
            else 0.0
        )
        class_metrics[lbl] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": tp + fn,
        }

    macro_p = sum(m["precision"] for m in class_metrics.values()) / len(LABELS)
    macro_r = sum(m["recall"] for m in class_metrics.values()) / len(LABELS)
    macro_f1 = sum(m["f1"] for m in class_metrics.values()) / len(LABELS)

    return {
        "accuracy": accuracy,
        "total": total,
        "correct": correct,
        "per_class": class_metrics,
        "macro": {"precision": macro_p, "recall": macro_r, "f1": macro_f1},
    }


def _metrics_by_category(results: list[dict]) -> dict[str, dict]:
    by_cat: dict[str, list] = defaultdict(list)
    for r in results:
        by_cat[r["category"]].append(r)
    return {cat: _compute_metrics(rows) for cat, rows in sorted(by_cat.items())}


# ── Formatters ─────────────────────────────────────────────────────────────


def _render_markdown(
    overall: dict, by_cat: dict[str, dict], timestamp: str, mode: str
) -> str:
    lines = [
        f"# Informe de Evaluación RAG — ReFlow",
        f"",
        f"**Fecha:** {timestamp}  ",
        f"**Modo:** {mode}  ",
        f"**Casos evaluados:** {overall['total']}  ",
        f"**Accuracy global:** {overall['accuracy']:.1%}  ",
        f"",
        f"## Métricas globales por clase",
        f"",
        f"| Clase | Precision | Recall | F1 | Support |",
        f"|-------|-----------|--------|----|---------|",
    ]
    for lbl in LABELS:
        m = overall["per_class"][lbl]
        lines.append(
            f"| {lbl} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} | {m['support']} |"
        )
    macro = overall["macro"]
    lines += [
        f"| **macro avg** | {macro['precision']:.3f} | {macro['recall']:.3f} | {macro['f1']:.3f} | {overall['total']} |",
        f"",
        f"## Accuracy por categoría",
        f"",
        f"| Categoría | Casos | Accuracy | F1 macro |",
        f"|-----------|-------|----------|----------|",
    ]
    for cat, m in by_cat.items():
        lines.append(
            f"| {cat} | {m['total']} | {m['accuracy']:.1%} | {m['macro']['f1']:.3f} |"
        )
    return "\n".join(lines) + "\n"


# ── Runner principal ────────────────────────────────────────────────────────


async def run_evaluation(
    limit: int | None = None,
    category: str | None = None,
    dry_run: bool = False,
) -> dict:
    from backend.agents.nodes.evaluator import evaluator_agent
    from backend.services.observability import get_langfuse, flush as langfuse_flush

    cases = _load_cases(EVAL_CSV, limit, category)
    logger.info(
        "Evaluando %d casos (modo %s)…",
        len(cases),
        "dry-run" if dry_run else "LLM real",
    )

    lf = get_langfuse()
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    # ID de traza raíz — se pasa como trace_id en cada span
    run_trace_id: str | None = None
    if lf:
        from langfuse import Langfuse

        run_trace_id = Langfuse.create_trace_id()
        logger.info("LangFuse: trace_id=%s", run_trace_id)

    results: list[dict] = []

    for i, row in enumerate(cases):
        case_id = row["case_id"]
        expected = row["expected_label"]
        cat = row["category"]
        max_days = int(row["max_return_days"])

        if dry_run:
            predicted = _deterministic_label(row)
        else:
            state = _build_state(row)
            allowed_conditions = row["allowed_conditions"].split("|")
            mock_policy = _build_mock_policy(cat, max_days, allowed_conditions)

            async def _mock_search(
                query: str, category: str = ""
            ) -> dict:  # noqa: E501
                return mock_policy

            try:
                with patch(
                    "backend.agents.nodes.evaluator.search_return_policy",
                    side_effect=_mock_search,
                ):
                    agent_result = await evaluator_agent(state)
                predicted = _result_to_label(agent_result)
            except Exception as exc:
                logger.warning("Caso %s falló: %s", case_id, exc)
                predicted = "error"

        match = expected == predicted
        results.append(
            {
                "case_id": case_id,
                "category": cat,
                "expected": expected,
                "predicted": predicted,
                "match": match,
                "rationale": row.get("rationale", ""),
            }
        )

        # ── LangFuse: span + scores por caso ──────────────────────────────
        if lf and run_trace_id:
            try:
                obs = lf.start_observation(
                    name=f"eval-case-{cat}",
                    as_type="evaluator",
                    input={
                        "case_id": case_id,
                        "category": cat,
                        "reason_category": row.get("reason_category"),
                        "days": row.get("days_since_delivery"),
                        "amount": row.get("refund_amount"),
                    },
                    output={
                        "expected": expected,
                        "predicted": predicted,
                        "match": match,
                    },
                    metadata={
                        "rationale": row.get("rationale", ""),
                        "is_frequent_returner": row.get("is_frequent_returner"),
                    },
                    trace_context={"trace_id": run_trace_id},
                )
                obs.end()
                lf.create_score(
                    trace_id=run_trace_id,
                    observation_id=obs.id,
                    name="label_match",
                    value=1.0 if match else 0.0,
                    data_type="NUMERIC",
                )
            except Exception as exc:
                logger.debug("LangFuse span error (caso %s): %s", case_id, exc)

        if (i + 1) % 50 == 0:
            logger.info("  %d/%d casos procesados…", i + 1, len(cases))

    overall = _compute_metrics(results)
    by_cat = _metrics_by_category(results)
    mismatches = [r for r in results if not r["match"]]

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "dry-run" if dry_run else "llm",
        "overall": overall,
        "by_category": by_cat,
        "mismatches": mismatches[:50],
    }

    # ── LangFuse: scores agregados en la traza raíz ────────────────────────
    if lf and run_trace_id:
        try:
            for metric_name, value in [
                ("accuracy", overall["accuracy"]),
                ("macro_f1", overall["macro"]["f1"]),
                ("macro_precision", overall["macro"]["precision"]),
                ("macro_recall", overall["macro"]["recall"]),
            ]:
                lf.create_score(
                    trace_id=run_trace_id,
                    name=metric_name,
                    value=value,
                    data_type="NUMERIC",
                )
            langfuse_flush()
            logger.info("LangFuse: métricas enviadas → trace_id=%s", run_trace_id)
        except Exception as exc:
            logger.warning("LangFuse flush error: %s", exc)

    # ── Guardar resultados ─────────────────────────────────────────────────
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = run_ts
    json_path = RESULTS_DIR / f"eval_report_{ts}.json"
    md_path = RESULTS_DIR / f"eval_report_{ts}.md"

    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    md_path.write_text(
        _render_markdown(overall, by_cat, ts, report["mode"]), encoding="utf-8"
    )

    logger.info("─" * 60)
    logger.info(
        "Accuracy: %.1f%%  |  Macro F1: %.3f",
        overall["accuracy"] * 100,
        overall["macro"]["f1"],
    )
    logger.info("Informe JSON → %s", json_path)
    logger.info("Informe MD  → %s", md_path)

    return report


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--limit", type=int, default=None, help="Limitar a los primeros N casos."
    )
    p.add_argument("--category", default=None, help="Evaluar solo esta categoría.")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Usar reglas deterministas en vez del LLM (no consume tokens, apto para CI).",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    report = asyncio.run(
        run_evaluation(
            limit=args.limit,
            category=args.category,
            dry_run=args.dry_run,
        )
    )
    # Exit code no-cero si accuracy < 70% (útil en CI)
    accuracy = report["overall"]["accuracy"]
    sys.exit(0 if accuracy >= 0.70 else 1)
