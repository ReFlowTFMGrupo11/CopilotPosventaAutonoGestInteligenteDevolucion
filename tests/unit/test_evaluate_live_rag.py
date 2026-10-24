"""Pruebas sin red para los juicios de recuperación del corpus."""

import pytest

from evaluation.golden.scripts.evaluate_live_rag import (
    evidence_rank,
    load_cases,
    validate_index,
)


def test_judgments_reference_existing_policy_text():
    assert len(load_cases()) == 4


def test_evidence_rank_requires_source_and_text():
    case = {"source_doc": "04_calzado.md", "evidence": "30 días naturales"}
    chunks = [
        {
            "chunk_text": "30 días naturales",
            "metadata": {"source_doc": "00_marco_general_devoluciones.md"},
        },
        {
            "chunk_text": "Calzado: 30 días naturales desde la entrega",
            "metadata": {"source_doc": "04_calzado.md"},
        },
    ]
    assert evidence_rank(case, chunks) == 2
    assert evidence_rank(case, chunks[:1]) is None
    assert evidence_rank(case, []) is None


def test_index_requires_ingestion_and_unique_positions():
    case = [{"source_doc": "04_calzado.md"}]
    with pytest.raises(ValueError, match="Faltan documentos"):
        validate_index(case, [])

    row = {"id": "a", "metadata": {"source_doc": "04_calzado.md", "chunk_index": 0}}
    assert validate_index(case, [row]) == {"a": row["metadata"]}
    with pytest.raises(ValueError, match="duplicados"):
        validate_index(case, [row, {**row, "id": "b"}])
