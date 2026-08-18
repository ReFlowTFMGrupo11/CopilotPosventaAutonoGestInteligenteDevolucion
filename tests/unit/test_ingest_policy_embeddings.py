"""Tests unitarios para dataset/rag/ingest_policy_embeddings.py.

Las funciones de chunking son puras (sin red ni BD) y se prueban tal cual.
Las que hablan con Supabase/OpenAI se prueban con mocks, sin credenciales
reales — verificar la inserción real contra un Supabase vivo queda fuera
del alcance de un test unitario (ver dataset/README.md).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from data.generate_dataset import POLICIES_DIR
from data.rag.ingest_policy_embeddings import (
    GENERAL_POLICY_DOC,
    MAX_CHUNK_TOKENS,
    _count_tokens,
    _get_active_policy_id,
    _replace_embeddings,
    _split_into_sections,
    chunk_markdown,
    ingest,
)


class TestSplitIntoSections:
    def test_splits_by_level_two_headers(self):
        md = "Título\n\nIntro.\n\n## Uno\n\nTexto uno.\n\n## Dos\n\nTexto dos.\n"
        sections = _split_into_sections(md)
        assert [header for header, _ in sections] == ["", "Uno", "Dos"]

    def test_drops_empty_sections(self):
        md = "## Vacía\n\n## Con contenido\n\nAlgo.\n"
        sections = _split_into_sections(md)
        assert [header for header, _ in sections] == ["Con contenido"]


class TestChunkMarkdown:
    def test_keeps_oversized_paragraph_as_its_own_chunk(self):
        """Un párrafo que ya por sí solo supera el máximo no se parte a ciegas."""
        huge_paragraph = "palabra de relleno " * 400  # muy por encima de MAX_CHUNK_TOKENS
        md = "## Grande\n\n" + huge_paragraph
        chunks = chunk_markdown(md)
        assert len(chunks) == 1
        assert huge_paragraph.strip() in chunks[0]

    def test_each_chunk_is_prefixed_with_its_section_header(self):
        md = "## Mi Sección\n\nPárrafo corto.\n"
        chunks = chunk_markdown(md)
        assert all(chunk.startswith("## Mi Sección") for chunk in chunks)

    def test_section_without_header_has_no_prefix(self):
        md = "Texto suelto antes de cualquier encabezado.\n"
        chunks = chunk_markdown(md)
        assert chunks == ["Texto suelto antes de cualquier encabezado."]

    def test_never_splits_a_paragraph_across_chunks(self):
        p1 = "Primer párrafo relevante. " * 10
        p2 = "Segundo párrafo relevante. " * 10
        md = f"## S\n\n{p1}\n\n{p2}"
        chunks = chunk_markdown(md)
        combined = " ".join(chunks)
        assert p1.strip() in combined
        assert p2.strip() in combined
        # Ninguno de los dos párrafos queda partido entre dos chunks distintos.
        assert any(p1.strip() in c for c in chunks)
        assert any(p2.strip() in c for c in chunks)

    def test_real_general_policy_doc_produces_reasonable_chunks(self):
        """Smoke test contra el documento real: ni un chunk gigante ni cientos de migajas."""
        text = (POLICIES_DIR / GENERAL_POLICY_DOC).read_text(encoding="utf-8")
        chunks = chunk_markdown(text)
        assert 5 <= len(chunks) <= 30
        assert all(chunk.strip() for chunk in chunks)
        # Ningún chunk se dispara muy por encima del máximo salvo el caso
        # documentado (párrafo ya oversized por sí solo, p.ej. la tabla).
        assert all(_count_tokens(chunk) <= MAX_CHUNK_TOKENS * 2 for chunk in chunks)


class TestGetActivePolicyId:
    @pytest.mark.asyncio
    async def test_returns_id_when_found(self):
        mock_client = MagicMock()
        resp = MagicMock(data=[{"id": "pol-123"}])
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute = AsyncMock(
            return_value=resp
        )

        result = await _get_active_policy_id(mock_client, "calzado")

        assert result == "pol-123"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        mock_client = MagicMock()
        resp = MagicMock(data=[])
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute = AsyncMock(
            return_value=resp
        )

        result = await _get_active_policy_id(mock_client, "categoria_inexistente")

        assert result is None


class TestReplaceEmbeddings:
    @pytest.mark.asyncio
    async def test_deletes_by_policy_id_then_inserts(self):
        mock_client = MagicMock()
        mock_client.table.return_value.delete.return_value.eq.return_value.execute = AsyncMock()
        mock_client.table.return_value.insert.return_value.execute = AsyncMock()

        inserted = await _replace_embeddings(
            mock_client, "pol-123", ["chunk uno", "chunk dos"], [[0.1, 0.2], [0.3, 0.4]], "01_x.md"
        )

        assert inserted == 2
        mock_client.table.return_value.delete.return_value.eq.assert_called_once_with("policy_id", "pol-123")
        mock_client.table.return_value.delete.return_value.eq.return_value.execute.assert_awaited_once()
        rows = mock_client.table.return_value.insert.call_args[0][0]
        assert len(rows) == 2
        assert rows[0] == {
            "policy_id": "pol-123",
            "chunk_text": "chunk uno",
            "embedding": [0.1, 0.2],
            "metadata": {"source_doc": "01_x.md", "chunk_index": 0},
        }

    @pytest.mark.asyncio
    async def test_deletes_by_null_policy_id_for_general_doc(self):
        mock_client = MagicMock()
        mock_client.table.return_value.delete.return_value.is_.return_value.execute = AsyncMock()
        mock_client.table.return_value.insert.return_value.execute = AsyncMock()

        await _replace_embeddings(mock_client, None, ["c1"], [[0.1]], "00_marco.md")

        mock_client.table.return_value.delete.return_value.is_.assert_called_once_with("policy_id", None)

    @pytest.mark.asyncio
    async def test_no_insert_call_when_no_chunks(self):
        mock_client = MagicMock()
        mock_client.table.return_value.delete.return_value.eq.return_value.execute = AsyncMock()

        inserted = await _replace_embeddings(mock_client, "pol-1", [], [], "doc.md")

        assert inserted == 0
        mock_client.table.return_value.insert.assert_not_called()


class TestIngestDryRun:
    """dry_run=True no debe tocar red ni BD (ni siquiera importar credenciales)."""

    @pytest.mark.asyncio
    async def test_dry_run_counts_without_network(self):
        total = await ingest(dry_run=True, only_category="calzado")
        assert total > 0

    @pytest.mark.asyncio
    async def test_only_category_still_includes_general_doc(self):
        general_chunks = len(chunk_markdown((POLICIES_DIR / GENERAL_POLICY_DOC).read_text(encoding="utf-8")))
        category_chunks = len(chunk_markdown((POLICIES_DIR / "04_calzado.md").read_text(encoding="utf-8")))

        total = await ingest(dry_run=True, only_category="calzado")

        assert total == general_chunks + category_chunks

    @pytest.mark.asyncio
    async def test_unknown_category_raises_instead_of_silently_skipping(self):
        """Antes de este fix, un --category con un typo no avisaba: solo
        ingería el marco general y parecía haber funcionado."""
        with pytest.raises(ValueError, match="Categoría desconocida"):
            await ingest(dry_run=True, only_category="categoria_que_no_existe")


class TestIngestSkipsMissingCategory:
    @pytest.mark.asyncio
    async def test_skips_category_without_active_policy_row(self):
        """Si return_policies no tiene fila activa para una categoría, se
        salta esa categoría (no falla el script entero) y no se le llama a
        embeddings/replace; el marco general sí se procesa (no depende de
        policy_id)."""
        with patch("data.rag.ingest_policy_embeddings.OpenAI", return_value=MagicMock()), \
             patch(
                 "data.rag.ingest_policy_embeddings.get_supabase_client",
                 new_callable=AsyncMock,
                 return_value=MagicMock(),
             ), \
             patch(
                 "data.rag.ingest_policy_embeddings._get_active_policy_id",
                 new_callable=AsyncMock,
                 return_value=None,
             ), \
             patch("data.rag.ingest_policy_embeddings._embed_texts") as mock_embed, \
             patch(
                 "data.rag.ingest_policy_embeddings._replace_embeddings", new_callable=AsyncMock
             ) as mock_replace:
            await ingest(only_category="calzado")

        mock_embed.assert_called_once()  # solo el marco general (policy_id=None)
        mock_replace.assert_awaited_once()
