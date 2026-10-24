"""Evaluación opt-in de recuperación real y, opcionalmente, decisión del evaluador.

Ejecutar desde la raíz: python -m evaluation.golden.scripts.evaluate_live_rag --live
Sin --live solo valida los juicios contra el corpus local (sin red ni coste).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[3]
CASES = ROOT / "evaluation" / "golden" / "live_rag_cases.json"
POLICIES = ROOT / "data" / "rag" / "policies"


def load_cases() -> list[dict]:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    if not cases:
        raise ValueError("No hay juicios de relevancia para evaluar.")
    for case in cases:
        source = (POLICIES / case["source_doc"]).resolve()
        if source.parent != POLICIES.resolve() or not source.is_file():
            raise ValueError(f"Documento desconocido: {case['source_doc']}")
        if (
            case["evidence"].casefold()
            not in source.read_text(encoding="utf-8").casefold()
        ):
            raise ValueError(
                f"Evidencia ausente en {case['source_doc']}: {case['evidence']}"
            )
    return cases


def evidence_rank(case: dict, chunks: list[dict]) -> int | None:
    """Posición del primer chunk con la evidencia indicada (no recall exhaustivo)."""
    for rank, chunk in enumerate(chunks, start=1):
        if (
            chunk["metadata"].get("source_doc") == case["source_doc"]
            and case["evidence"].casefold() in chunk["chunk_text"].casefold()
        ):
            return rank
    return None


def validate_index(cases: list[dict], rows: list[dict]) -> dict[str, dict]:
    """Impide confundir un índice ausente/duplicado con fallos de recuperación."""
    if len(rows) >= 1000:
        raise ValueError("El índice supera 1000 filas; no se puede verificar completo.")
    metadata = {row["id"]: row["metadata"] for row in rows}
    indexed_docs = {row["metadata"].get("source_doc") for row in rows}
    missing = {case["source_doc"] for case in cases} - indexed_docs
    if missing:
        raise ValueError(
            f"Faltan documentos en el índice; ingestar primero: {sorted(missing)}"
        )
    positions = [
        (row["metadata"].get("source_doc"), row["metadata"].get("chunk_index"))
        for row in rows
    ]
    if len(positions) != len(set(positions)) or len(metadata) != len(rows):
        raise ValueError("El índice contiene chunks duplicados.")
    return metadata


async def evaluate_retrieval(cases: list[dict]) -> None:
    from backend.agents.nodes.evaluator import _build_rag_query
    from backend.services.policy_service import (
        list_policy_embedding_metadata,
        search_return_policy,
    )
    from data.rag.ingest_policy_embeddings import chunk_markdown

    rows = await list_policy_embedding_metadata()
    metadata = validate_index(cases, rows)
    hits = reciprocal_rank = empty = latency = 0
    local_chunks: dict[str, list[str]] = {}
    for case in cases:
        query = _build_rag_query(
            case["category"], case["reason_category"], case["condition"]
        )
        started = time.perf_counter()
        response = await search_return_policy(query, category=case["category"])
        latency += time.perf_counter() - started
        chunks = response["semantic_results"] or []
        ids = [chunk["id"] for chunk in chunks]
        if ids:
            if not set(ids) <= metadata.keys() or len(ids) != len(set(ids)):
                raise ValueError(
                    "Índice inconsistente: faltan metadatos o hay chunks duplicados."
                )
            for chunk in chunks:
                chunk["metadata"] = metadata[chunk["id"]]
                if chunk["metadata"].get("category") not in (
                    case["category"],
                    "general",
                ):
                    raise ValueError(
                        "El filtro de categoría de pgvector devolvió otra categoría."
                    )
                source_doc = chunk["metadata"].get("source_doc", "")
                source = (POLICIES / source_doc).resolve()
                if source.parent != POLICIES.resolve() or not source.is_file():
                    raise ValueError(f"Documento del índice desconocido: {source_doc}")
                if source_doc not in local_chunks:
                    local_chunks[source_doc] = chunk_markdown(
                        source.read_text(encoding="utf-8")
                    )
                index = chunk["metadata"].get("chunk_index")
                if (
                    not isinstance(index, int)
                    or index < 0
                    or index >= len(local_chunks[source_doc])
                    or local_chunks[source_doc][index] != chunk["chunk_text"]
                ):
                    raise ValueError(
                        f"Índice desactualizado: reingestar {source_doc} antes de evaluar."
                    )
        rank = evidence_rank(case, chunks)
        hits += rank is not None
        reciprocal_rank += 1 / rank if rank else 0
        empty += not chunks
        print(
            f"{case['category']} / {case['source_doc']}: "
            f"rango={rank or '-'} chunks={len(chunks)}"
        )
    n = len(cases)
    print(
        f"Recuperación real: hit@5={hits}/{n} ({hits/n:.1%}), "
        f"MRR@5={reciprocal_rank/n:.3f}, vacíos={empty}/{n}, "
        f"latencia media={latency/n:.2f}s"
    )


async def evaluate_decisions(limit: int) -> None:
    from backend.agents.nodes.evaluator import evaluator_agent
    from backend.services import policy_service
    from evaluation.golden.scripts.evaluate_evaluator_agent import (
        _build_state,
        _first_item_reason,
        _load_cases,
        _result_to_label,
        EVAL_CSV,
    )

    rows = _load_cases(EVAL_CSV, limit=None, category=None)
    if not rows:
        raise ValueError("El dataset golden no contiene casos.")
    correct = evaluated = skipped = 0
    policies: dict[str, dict] = {}
    for row in rows:
        if evaluated >= limit:
            break
        category = row["category"]
        if category not in policies:
            policies[category] = await policy_service.get_policy_info(category) or {}
        policy = policies[category]
        if (
            not policy
            or policy.get("max_return_days") != int(row["max_return_days"])
            or set(policy.get("allowed_conditions") or [])
            != set(row["allowed_conditions"].split("|"))
            or float(policy.get("restocking_fee_percent") or 0) != 0
        ):
            skipped += 1
            print(
                f"{row['case_id']}: excluido (política activa distinta del caso golden)"
            )
            continue
        # Solo se sustituye el transporte MCP por el servicio REAL: no hay mocks
        # de búsqueda ni de políticas; se evita escribir telemetría en llm_usage.
        with (
            patch(
                "backend.agents.nodes.evaluator.get_policy_info",
                policy_service.get_policy_info,
            ),
            patch(
                "backend.agents.nodes.evaluator.search_return_policy",
                policy_service.search_return_policy,
            ),
            patch(
                "backend.agents.usage_tracking.usage_service.log_llm_usage",
                new_callable=AsyncMock,
            ),
        ):
            result = await evaluator_agent(_build_state(row))
        predicted = _result_to_label(result)
        correct += predicted == row["expected_label"]
        evaluated += 1
        print(
            f"{row['case_id']}: esperado={row['expected_label']} obtenido={predicted} "
            f"elegible={result['items_eligibility'][0]['is_eligible']} "
            f"razón={_first_item_reason(result)}"
        )
    if not evaluated:
        raise ValueError(
            "Ningún caso comparable: revisar políticas activas y dataset golden."
        )
    print(
        f"Decisión con RAG y LLM reales: accuracy={correct}/{evaluated} "
        f"({correct/evaluated:.1%}); excluidos={skipped}"
    )
    print(
        "La política estructurada también incluye texto completo: accuracy no prueba atribución al retrieval."
    )


async def run_live(cases: list[dict], *, with_llm: bool, limit: int) -> None:
    await evaluate_retrieval(cases)
    if with_llm:
        await evaluate_decisions(limit)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Consultar Supabase y generar embeddings reales (con coste).",
    )
    parser.add_argument(
        "--with-llm",
        action="store_true",
        help="Además, evaluar decisiones golden con LLM real (con coste).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Máximo de casos golden comparables con LLM (por defecto 5).",
    )
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 480:
        parser.error("--limit debe estar entre 1 y 480")
    if args.with_llm and not args.live:
        parser.error("--with-llm requiere --live")
    cases = load_cases()
    if not args.live:
        print(
            f"{len(cases)} juicios validados contra el corpus. Sin llamadas de red; use --live para medir."
        )
        return

    # Settings carga las credenciales solo en el modo opt-in; no se imprimen.
    from backend.config import get_settings

    settings = get_settings()
    if (
        not settings.openai_api_key
        or not settings.supabase_url
        or not settings.supabase_service_key
    ):
        parser.error(
            "--live requiere OPENAI_API_KEY, SUPABASE_URL y SUPABASE_SERVICE_KEY"
        )
    asyncio.run(run_live(cases, with_llm=args.with_llm, limit=args.limit))


if __name__ == "__main__":
    main()
