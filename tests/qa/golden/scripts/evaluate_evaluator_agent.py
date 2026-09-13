"""
Evaluador end-to-end del Agente Evaluador de Políticas contra el golden dataset.

Pese al nombre histórico ("evaluate_rag"), este script NO ejecuta ninguna
búsqueda vectorial real: mockea search_return_policy() devolviendo el texto
de política ya resuelto a mano por categoría (_build_mock_policy), así que
no mide la calidad del retrieval. Lo que sí mide es si, dado el contexto de
política correcto, evaluator_agent() decide bien (LLM real o reglas
deterministas en --dry-run). El test real del RAG (chunking/ingesta) vive en
tests/unit/test_ingest_policy_embeddings.py.

Lee los 480 casos de tests/qa/golden/eval_cases.csv, construye un estado
mínimo por caso, y ejecuta evaluator_agent con el LLM real (gpt-5-mini).
Calcula precisión, recall y F1 por clase y por categoría, más las 4
métricas adicionales de más abajo.

## Dónde se ven las métricas

Este script NO escribe ningún fichero local (ni JSON ni Markdown): todas
las métricas, por caso y agregadas, se mandan como `score` a LangFuse (si
está configurado, ver requisitos más abajo) — la traza raíz agrupa toda la
ejecución, cada caso es un span con sus propios scores. Sin LangFuse
configurado (p. ej. en CI, `--dry-run`), el único resultado persistente es
el exit code de `accuracy` (ver `if __name__ == "__main__"`, calculado en
memoria); las métricas de esa ejecución concreta solo se ven en el log de
consola, no se guardan en ningún sitio -- si el objetivo es guardar un
histórico, hazlo vía LangFuse, no relanzando el script y mirando la
terminal.

Uso:
    python -m tests.qa.golden.scripts.evaluate_evaluator_agent                  # todos los casos
    python -m tests.qa.golden.scripts.evaluate_evaluator_agent --limit 50       # primeros N casos
    python -m tests.qa.golden.scripts.evaluate_evaluator_agent --category calzado
    python -m tests.qa.golden.scripts.evaluate_evaluator_agent --dry-run        # lógica determinista, sin LLM

Modo --dry-run: en vez de llamar al LLM, aplica las reglas deterministas
directamente sobre las columnas del CSV (plazo, importe HITL, is_frequent_returner)
para validar que el golden dataset es internamente consistente.  Ideal para CI.

Requisitos (solo para el modo real):
    OPENAI_API_KEY en .env

## Métricas de evaluación (ver docs/defensaTFM/defenderDatos.md)

De las 6 categorías de la tabla de evaluación del TFM, este script cubre:
todas las que se implementan se mandan como `score` a LangFuse (por caso
y/o agregado en la traza raíz, ver "Dónde se ven las métricas" más
arriba) -- ninguna vive solo en un fichero local.

- **Task success**: sí (accuracy/precision/recall/F1 por clase, la métrica
  original de este script).
- **Tool accuracy**: sí, `_expected_tool_called()` — evaluator_agent solo
  debería llamar a `search_return_policy()` (Fase 2, RAG narrativo) cuando
  el pre-check determinista (Fase 1) NO resuelve el caso él solo, es decir,
  cuando `expected_label != "invalid"` (ver docstring de `evaluator_agent`
  en backend/agents/nodes/evaluator.py). No hace falta una columna
  `expected_tool` nueva en el CSV: se deriva de `expected_label`, que ya
  sale de la misma lógica de negocio (`classify_case()` en
  `generate_dataset.py` replica `deterministic_check()`).
- **Contains**: sí, pero deliberadamente acotado — `_expected_keywords()`
  solo comprueba la palabra "plazo" en `eligibility_reason` para casos
  `invalid` por fuera de plazo (Fase 1, texto 100% determinista de
  `policy_rules.py`, sin LLM de por medio). NO se comprueban palabras para
  higiene/condición (redacción más variable, check frágil) ni para casos
  `human_review`/`valid` que sí pasan por el LLM (Fase 2): ahí
  `eligibility_reason` es razonamiento libre sobre elegibilidad de
  política, no una plantilla fija sobre el motivo de HITL (importe/cliente
  frecuente) — el LLM nunca recibe esos umbrales como instrucción
  explícita, así que comprobarlos ahí daría falsos negativos por diseño
  del prompt, no por un fallo real del agente.
- **Costo**/**Latencia**: sí, por caso — se mockea
  `usage_service.log_llm_usage()` (nunca escribe en la BD real: mismo
  motivo por el que se mockean `search_return_policy`/`get_policy_info`,
  evitar efectos secundarios reales en una evaluación) para capturar
  tokens/modelo de cada llamada real al LLM y calcular su coste con
  `pricing.py`; la latencia mide el `evaluator_agent()` completo por caso
  (incluye el mock de RAG, que es ~instantáneo, así que en la práctica es
  la latencia real del LLM).
- **LLM-as-judge**: decisión consciente de NO implementarlo. Las
  `expected_label` del golden dataset salen de `classify_case()` — reglas
  Python deterministas, no el juicio de otro LLM — precisamente para tener
  un "ground truth" reproducible y auditable byte a byte (dos ejecuciones
  del generador con el mismo `SEED` dan el mismo dataset). Introducir un
  LLM-juez añadiría no-determinismo justo en la pieza que se usa como
  referencia para medir al LLM evaluado — ver docs/defensaTFM/
  defenderDatos.md.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from dotenv import load_dotenv

load_dotenv(override=True)

from backend.services import pricing  # noqa: E402 -- tras load_dotenv, ver Settings

# ── Rutas ──────────────────────────────────────────────────────────────────
# parents[4]: scripts/ -> golden/ -> qa/ -> tests/ -> repo root
REPO_ROOT = Path(__file__).resolve().parents[4]
EVAL_CSV = REPO_ROOT / "tests" / "qa" / "golden" / "eval_cases.csv"
POLICIES_DIR = REPO_ROOT / "data" / "rag" / "policies"

# ── Umbrales deterministas (deben coincidir con la lógica del agente) ──────
HITL_AMOUNT_THRESHOLD = 100.0  # €  → human_review
BORDER_ZONE_DAYS = 5  # plazo ± 5 días → human_review (zona frontera)

LABELS = ["valid", "invalid", "human_review"]

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────


def _load_cases(csv_path: Path, limit: int | None, category: str | None) -> list[dict]:
    """Carga los casos del CSV, filtrando opcionalmente por categoría y limitando el número de filas.

    Args:
        csv_path: Ruta al CSV de casos golden.
        limit: Si se indica, se queda solo con los primeros N casos (tras filtrar).
        category: Si se indica, se queda solo con las filas de esa categoría.
    """
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
    # days_since_delivery viene directo de la columna del CSV, sin pasar por
    # una fecha fabricada: evaluator_agent ya no calcula esto él mismo (ver
    # orders_service.get_order_details(), que lo precalcula al ser el único
    # llamador vía MCP) -- lee order["days_since_delivery"] directamente. Es
    # más robusto que la fecha simulada de antes (delivered_at = ahora -
    # days), que era una bomba de relojería si "ahora" y el cálculo interno
    # de evaluator.py no se ejecutaban en el mismo instante exacto.
    days = int(row["days_since_delivery"])
    now = datetime.now(timezone.utc)
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
                "days_since_delivery": days,
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
        # Solo para que el guard de usage_tracking.py::_log_usage() ("sin
        # thread_id no hay sesión a la que atribuir el gasto") no descarte
        # la llamada -- log_llm_usage() está mockeado más abajo (ver
        # run_evaluation), nunca escribe en la BD real. Necesario para
        # medir Costo/Latencia por caso (ver docstring del módulo).
        "thread_id": f"eval-{row['case_id']}",
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


def _expected_tool_called(row: dict) -> bool:
    """Si evaluator_agent debería llamar a ``search_return_policy()`` (Fase
    2, RAG narrativo) para este caso.

    Ver el docstring de ``evaluator_agent`` (backend/agents/nodes/evaluator.py):
    el pre-check determinista (Fase 1, ``get_policy_info`` + ``deterministic_check()``)
    resuelve el caso ENTERO sin RAG cuando el veredicto es "invalid" — ningún
    contexto adicional cambiaría ese veto. Solo cuando el veredicto queda en
    zona gris ("valid"/"human_review") el caso pasa a la Fase 2 y llama a
    ``search_return_policy()``.

    No hace falta una columna ``expected_tool`` nueva en el CSV:
    ``expected_label`` ya sale de ``classify_case()`` (generate_dataset.py),
    que replica las mismas reglas de negocio que ``deterministic_check()``
    (policy_rules.py) — por eso "invalid" en el CSV predice de forma fiable
    "sin llamada RAG" en el agente real.
    """
    return row["expected_label"] != "invalid"


def _expected_keywords(row: dict) -> list[str]:
    """Palabra clave que DEBERÍA aparecer en el ``eligibility_reason`` real
    si el caso se decide por plazo, o lista vacía si no aplica ningún check.

    Deliberadamente acotado: solo cubre casos "invalid" resueltos en la
    Fase 1 (pre-check determinista, sin LLM) cuyo motivo es el plazo —
    ``rule_deadline``/``rule_deadline_borderline`` (policy_rules.py) usan
    literalmente la palabra "plazo" en su mensaje, así que es un check
    robusto contra código propio y estable.

    NO se comprueban palabras para higiene/condición (la redacción de
    ``rule_hygiene``/``rule_condition_allowed`` varía más entre casos, sería
    un check más frágil que útil) ni para casos "valid"/"human_review" que
    sí pasan por el LLM (Fase 2): ahí ``eligibility_reason`` es razonamiento
    libre sobre elegibilidad de política. En particular, el motivo de HITL
    por importe/cliente frecuente (``rule_high_amount``/
    ``rule_frequent_returner``) NUNCA se expone al LLM como instrucción
    explícita — solo decide ``needs_admin_approval`` a nivel de solicitud,
    no el texto de ningún item — así que comprobar esas palabras ahí daría
    falsos negativos por diseño del prompt, no por un fallo real del agente.
    """
    if row["expected_label"] != "invalid":
        return []
    days = int(row["days_since_delivery"])
    max_days = int(row["max_return_days"])
    if days > max_days:
        return ["plazo"]
    return []


def _first_item_reason(result: dict[str, Any]) -> str:
    """``eligibility_reason`` del primer item (casos single-item del CSV),
    o cadena vacía si no hay ninguno."""
    items = result.get("items_eligibility") or []
    if not items:
        return ""
    return items[0].get("eligibility_reason") or ""


def _result_to_label(result: dict[str, Any]) -> str:
    """Convierte la salida de evaluator_agent en una etiqueta comparable.

    ``needs_admin_approval`` (backend/agents/nodes/evaluator.py) es el
    veredicto "human_review" de deterministic_check() — 100% determinista,
    independiente de lo que el LLM haya puesto en ``is_eligible`` para ese
    item. Debe comprobarse ANTES que ``is_eligible``: un item puede llegar
    con is_eligible=False y aun así estar en zona de HITL (importe > umbral,
    zona frontera de plazo, cliente frecuente) — deterministic_check() no
    toca is_eligible cuando el veredicto es "human_review" (ver comentario
    en evaluator_agent), así que ese campo no es fiable por sí solo para
    distinguir "invalid" de "human_review". Antes de este fix, cualquier
    caso HITL donde el LLM marcara is_eligible=False se contaba como
    "invalid" — falso negativo sistemático contra el golden dataset, cuyo
    expected_label sale de la misma lógica determinista (data/generate_dataset.py).
    """
    if result.get("needs_admin_approval"):
        return "human_review"

    items = result.get("items_eligibility", [])
    if not items:
        return "invalid"

    # Tomamos el primer item (casos single-item del CSV)
    item = items[0]
    if not item.get("is_eligible"):
        return "invalid"

    return "valid"


# ── Métricas ───────────────────────────────────────────────────────────────


def _compute_metrics(results: list[dict]) -> dict:
    """Calcula accuracy, precision, recall y F1 por clase y macro-average."""
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
    """Agrupa los resultados por categoría y calcula las métricas de cada grupo."""
    by_cat: dict[str, list] = defaultdict(list)
    for r in results:
        by_cat[r["category"]].append(r)
    return {cat: _compute_metrics(rows) for cat, rows in sorted(by_cat.items())}


def _compute_extra_metrics(results: list[dict]) -> dict:
    """Tool accuracy, contains, costo y latencia agregados (ver docstring
    del módulo). Todo a None/0 en modo --dry-run, donde no se llama a
    evaluator_agent ni a los mocks -- ninguno de estos campos tiene sentido
    sin una invocación real.

    ``*_n`` documenta explícitamente el denominador de cada ratio: ni
    tool_accuracy ni contains_accuracy se calculan sobre los 480 casos --
    solo sobre el subconjunto con una expectativa bien definida (ver
    ``_expected_tool_called``/``_expected_keywords``), y ocultar ese
    denominador daría una falsa sensación de cobertura total.
    """
    tool_checked = [r["tool_match"] for r in results if r.get("tool_match") is not None]
    contains_checked = [
        r["contains_match"] for r in results if r.get("contains_match") is not None
    ]
    latencies = [r["latency_ms"] for r in results if r.get("latency_ms") is not None]
    llm_calls = sum(1 for r in results if r.get("llm_called"))
    total_cost_eur = sum(r.get("cost_eur") or 0.0 for r in results)

    return {
        "tool_accuracy": (
            (sum(tool_checked) / len(tool_checked)) if tool_checked else None
        ),
        "tool_accuracy_n": len(tool_checked),
        "contains_accuracy": (
            (sum(contains_checked) / len(contains_checked))
            if contains_checked
            else None
        ),
        "contains_accuracy_n": len(contains_checked),
        "total_cost_eur": round(total_cost_eur, 6),
        "llm_calls": llm_calls,
        "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else None,
    }


# ── Runner principal ────────────────────────────────────────────────────────


async def run_evaluation(
    limit: int | None = None,
    category: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Ejecuta la evaluación completa del golden dataset y genera el informe.

    Carga los casos filtrados y, por cada uno, obtiene la etiqueta predicha
    (reglas deterministas en ``dry_run``, o ``evaluator_agent`` con el LLM
    real y ``search_return_policy`` mockeado en caso contrario), comparándola
    con la etiqueta esperada del CSV. Si LangFuse está configurado, registra
    un span y todas las métricas de ese caso (label_match, tool_match,
    contains_match, cost_eur, latency_ms) como scores, más las métricas
    agregadas (accuracy, precision/recall/F1 por clase, accuracy por
    categoría, tool/contains accuracy, coste/latencia totales) en la traza
    raíz. No escribe ningún fichero local: si LangFuse no está configurado,
    el único resultado persistente es el exit code de ``__main__`` (basado
    en accuracy, calculado en memoria) — ver docstring del módulo.

    Returns:
        ``{"mode": "dry-run"|"llm", "overall": <de _compute_metrics>}`` —
        lo mínimo que necesita ``__main__`` para el exit code.
    """
    from backend.agents.nodes.evaluator import evaluator_agent
    from backend.services.observability import get_langfuse, flush as langfuse_flush

    cases = _load_cases(EVAL_CSV, limit, category)
    logger.info(
        "Evaluando %d casos (modo %s)…",
        len(cases),
        "dry-run" if dry_run else "LLM real",
    )

    lf = get_langfuse()
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

        tool_match: bool | None = None
        contains_match: bool | None = None
        cost_eur: float | None = None
        latency_ms: int | None = None
        llm_called = False

        if dry_run:
            predicted = _deterministic_label(row)
        else:
            state = _build_state(row)
            allowed_conditions = row["allowed_conditions"].split("|")
            mock_policy = _build_mock_policy(cat, max_days, allowed_conditions)

            tool_called_flag = {"value": False}

            async def _mock_search(
                query: str, category: str = "", thread_id: str = ""
            ) -> dict:  # noqa: E501
                """Sustituye a search_return_policy() devolviendo la policy mockeada de este caso."""
                tool_called_flag["value"] = True
                return mock_policy

            async def _mock_policy_info(category: str) -> dict:
                """Sustituye a get_policy_info() (pre-check determinista, ver evaluator.py)."""
                return mock_policy.get("policy_info") or {}

            # Captura tokens/modelo de cada llamada real al LLM sin escribir
            # en la BD real -- mismo motivo que mockear las tools de RAG:
            # una evaluación no debe tener efectos secundarios reales (ver
            # docstring del módulo, sección Costo/Latencia).
            captured_usage: list[dict[str, Any]] = []

            async def _fake_log_llm_usage(**kwargs: Any) -> None:
                captured_usage.append(kwargs)

            start = time.perf_counter()
            try:
                with patch(
                    "backend.agents.nodes.evaluator.get_policy_info",
                    side_effect=_mock_policy_info,
                ), patch(
                    "backend.agents.nodes.evaluator.search_return_policy",
                    side_effect=_mock_search,
                ), patch(
                    "backend.agents.usage_tracking.usage_service.log_llm_usage",
                    new=AsyncMock(side_effect=_fake_log_llm_usage),
                ):
                    agent_result = await evaluator_agent(state)
                latency_ms = int((time.perf_counter() - start) * 1000)
                predicted = _result_to_label(agent_result)

                tool_match = tool_called_flag["value"] == _expected_tool_called(row)

                expected_kw = _expected_keywords(row)
                if expected_kw:
                    reason_text = _first_item_reason(agent_result).lower()
                    contains_match = all(kw in reason_text for kw in expected_kw)

                llm_called = bool(captured_usage)
                cost_eur = sum(
                    (
                        pricing.estimate_cost_eur(
                            u.get("model", ""),
                            u.get("input_tokens", 0),
                            u.get("output_tokens", 0),
                        )
                        or 0.0
                    )
                    for u in captured_usage
                )
            except Exception as exc:
                latency_ms = int((time.perf_counter() - start) * 1000)
                logger.warning("Caso %s falló: %s", case_id, exc)
                predicted = "error"

        match = expected == predicted
        # Solo se guardan los campos que _compute_metrics()/_metrics_by_category()/
        # _compute_extra_metrics() leen de verdad más abajo -- "case_id",
        # "match" y "rationale" NO se guardan aquí porque nada los vuelve a
        # leer del dict (case_id/rationale ya se usan directamente de
        # row/variables locales para el score de LangFuse de abajo; "match"
        # también se recalcula desde expected/predicted, nunca desde este
        # dict). Guardarlos sería código muerto.
        results.append(
            {
                "category": cat,
                "expected": expected,
                "predicted": predicted,
                "tool_match": tool_match,
                "contains_match": contains_match,
                "cost_eur": cost_eur,
                "latency_ms": latency_ms,
                "llm_called": llm_called,
            }
        )

        # ── LangFuse: span + scores por caso ──────────────────────────────
        # Todas las métricas por caso van aquí, no a un fichero local: si no
        # se manda a Langfuse (o no cabe como score agregado, ver más abajo),
        # no se calcula ni se guarda en ningún sitio (ver docstring del
        # módulo, "Dónde se ven las métricas").
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
                if tool_match is not None:
                    lf.create_score(
                        trace_id=run_trace_id,
                        observation_id=obs.id,
                        name="tool_match",
                        value=1.0 if tool_match else 0.0,
                        data_type="NUMERIC",
                    )
                if contains_match is not None:
                    lf.create_score(
                        trace_id=run_trace_id,
                        observation_id=obs.id,
                        name="contains_match",
                        value=1.0 if contains_match else 0.0,
                        data_type="NUMERIC",
                    )
                if cost_eur is not None:
                    lf.create_score(
                        trace_id=run_trace_id,
                        observation_id=obs.id,
                        name="cost_eur",
                        value=cost_eur,
                        data_type="NUMERIC",
                    )
                if latency_ms is not None:
                    lf.create_score(
                        trace_id=run_trace_id,
                        observation_id=obs.id,
                        name="latency_ms",
                        value=float(latency_ms),
                        data_type="NUMERIC",
                    )
            except Exception as exc:
                logger.debug("LangFuse span error (caso %s): %s", case_id, exc)

        if (i + 1) % 50 == 0:
            logger.info("  %d/%d casos procesados…", i + 1, len(cases))

    overall = _compute_metrics(results)
    by_cat = _metrics_by_category(results)
    extra = _compute_extra_metrics(results)

    # ── LangFuse: scores agregados en la traza raíz ────────────────────────
    # Cada métrica agregada calculada por este script se manda aquí -- es la
    # única forma en que este script "guarda" un resultado (ver docstring
    # del módulo). Sin LangFuse configurado (p. ej. en CI), estos scores
    # simplemente no se mandan a ningún sitio; el exit code (accuracy, más
    # abajo en __main__) sigue funcionando igual, en memoria.
    if lf and run_trace_id:
        try:
            for metric_name, value in [
                ("accuracy", overall["accuracy"]),
                ("macro_f1", overall["macro"]["f1"]),
                ("macro_precision", overall["macro"]["precision"]),
                ("macro_recall", overall["macro"]["recall"]),
                ("tool_accuracy", extra["tool_accuracy"]),
                ("contains_accuracy", extra["contains_accuracy"]),
                ("total_cost_eur", extra["total_cost_eur"]),
                ("avg_latency_ms", extra["avg_latency_ms"]),
            ]:
                if value is None:
                    continue
                lf.create_score(
                    trace_id=run_trace_id,
                    name=metric_name,
                    value=value,
                    data_type="NUMERIC",
                )
            # Precision/recall/F1 por clase: mismo nombre de score para las
            # 3 clases, diferenciadas por metadata -- evita crear un tipo de
            # score distinto por clase (mismo criterio que score_tool_call en
            # observability.py, ver su docstring).
            for lbl in LABELS:
                m = overall["per_class"][lbl]
                for metric_name in ("precision", "recall", "f1"):
                    lf.create_score(
                        trace_id=run_trace_id,
                        name=metric_name,
                        value=m[metric_name],
                        data_type="NUMERIC",
                        metadata={"label": lbl},
                    )
            # Accuracy por categoría: mismo criterio, metadata={"category": cat}.
            for cat, m in by_cat.items():
                lf.create_score(
                    trace_id=run_trace_id,
                    name="category_accuracy",
                    value=m["accuracy"],
                    data_type="NUMERIC",
                    metadata={"category": cat},
                )
            langfuse_flush()
            logger.info("LangFuse: métricas enviadas → trace_id=%s", run_trace_id)
        except Exception as exc:
            logger.warning("LangFuse flush error: %s", exc)

    logger.info("─" * 60)
    logger.info(
        "Accuracy: %.1f%%  |  Macro F1: %.3f",
        overall["accuracy"] * 100,
        overall["macro"]["f1"],
    )
    if not dry_run:
        logger.info(
            "Tool accuracy: %s (n=%d)  |  Contains: %s (n=%d)  |  "
            "Coste total: %.6f€ (%d llamadas al LLM)  |  Latencia media: %s",
            (
                f"{extra['tool_accuracy']:.1%}"
                if extra["tool_accuracy"] is not None
                else "—"
            ),
            extra["tool_accuracy_n"],
            (
                f"{extra['contains_accuracy']:.1%}"
                if extra["contains_accuracy"] is not None
                else "—"
            ),
            extra["contains_accuracy_n"],
            extra["total_cost_eur"],
            extra["llm_calls"],
            (
                f"{extra['avg_latency_ms']} ms"
                if extra["avg_latency_ms"] is not None
                else "—"
            ),
        )
    if not lf:
        logger.info(
            "LangFuse no configurado: las métricas de esta ejecución solo se "
            "ven en este log (nunca se guardan en un fichero local, ver "
            "docstring del módulo)."
        )

    return {"mode": "dry-run" if dry_run else "llm", "overall": overall}


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
