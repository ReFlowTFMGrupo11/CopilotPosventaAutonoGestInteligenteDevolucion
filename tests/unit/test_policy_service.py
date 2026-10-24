"""Tests unitarios para backend.services.policy_service.

Hueco de cobertura real cerrado al dividir supabase_service.py por dominio
(ver docs/REMAINING_TASKS.md #3/#4): get_policy_info/search_return_policy
no tenían ningún test dedicado en el fichero original.

search_return_policy() mockea openai.OpenAI (import local dentro de la
función, ver policy_service.py) y get_langfuse() -- nunca llama a la API
real de OpenAI ni a Supabase.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.policy_service import get_policy_info, search_return_policy


def _make_sync_supabase_client():
    """Cliente fake con builder sync y execute async, como supabase real."""
    client = MagicMock()
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.single.return_value = query
    client.table.return_value = query
    client.rpc.return_value = query
    return client, query


class TestGetPolicyInfo:
    @pytest.mark.asyncio
    async def test_categoria_vacia_devuelve_none_sin_llamar_a_la_bd(self):
        with patch(
            "backend.services.policy_service.get_supabase_client"
        ) as mock_get_client:
            result = await get_policy_info("")

        assert result is None
        mock_get_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_devuelve_la_fila_de_policy_encontrada(self):
        mock_client, query = _make_sync_supabase_client()
        query.execute = AsyncMock(
            return_value=MagicMock(
                data={
                    "category": "cosmetica_perfumeria",
                    "max_return_days": 21,
                    "allowed_conditions": ["unopened", "defective"],
                }
            )
        )

        with patch(
            "backend.services.policy_service.get_supabase_client",
            return_value=mock_client,
        ):
            result = await get_policy_info("cosmetica_perfumeria")

        assert result["max_return_days"] == 21
        query.eq.assert_any_call("category", "cosmetica_perfumeria")
        query.eq.assert_any_call("active", True)


class TestSearchReturnPolicy:
    def _patched_env(self, mock_supabase_client, embedding_vector=None):
        """Contexto con todo lo externo mockeado: Langfuse desactivado,
        openai.OpenAI parcheado, cliente Supabase fake, y get_policy_info
        (del propio módulo) devolviendo un valor fijo."""
        if embedding_vector is None:
            embedding_vector = [0.1, 0.2, 0.3]

        fake_openai_client = MagicMock()
        fake_openai_client.embeddings.create.return_value = SimpleNamespace(
            data=[SimpleNamespace(embedding=embedding_vector)]
        )
        fake_openai_cls = MagicMock(return_value=fake_openai_client)

        settings = SimpleNamespace(
            openai_api_key=None,
            rag_match_threshold=0.5,
            rag_embedding_model="text-embedding-3-small",
        )

        return (
            patch("backend.services.observability.get_langfuse", return_value=None),
            patch("openai.OpenAI", fake_openai_cls),
            patch(
                "backend.services.policy_service.get_supabase_client",
                return_value=mock_supabase_client,
            ),
            patch(
                "backend.services.policy_service.get_settings",
                return_value=settings,
            ),
            fake_openai_client,
        )

    @pytest.mark.asyncio
    async def test_devuelve_query_categoria_y_resultados(self):
        mock_client, query = _make_sync_supabase_client()
        query.execute = AsyncMock(
            return_value=MagicMock(
                data=[{"chunk_text": "texto de política", "similarity": 0.8}]
            )
        )

        with patch(
            "backend.services.policy_service.get_policy_info",
            new=AsyncMock(return_value={"max_return_days": 30}),
        ):
            p1, p2, p3, p4, _ = self._patched_env(mock_client)
            with p1, p2, p3, p4:
                result = await search_return_policy(
                    query="política de devolución en electronica_informatica",
                    category="electronica_informatica",
                    thread_id="thread-1",
                )

        assert result["query"] == "política de devolución en electronica_informatica"
        assert result["category"] == "electronica_informatica"
        assert result["semantic_results"] == [
            {"chunk_text": "texto de política", "similarity": 0.8}
        ]
        assert result["policy_info"] == {"max_return_days": 30}

    @pytest.mark.asyncio
    async def test_pasa_el_match_threshold_de_settings_al_rpc(self):
        mock_client, query = _make_sync_supabase_client()
        query.execute = AsyncMock(return_value=MagicMock(data=[]))

        with patch(
            "backend.services.policy_service.get_policy_info",
            new=AsyncMock(return_value=None),
        ):
            p1, p2, p3, p4, _ = self._patched_env(mock_client)
            with p1, p2, p3, p4:
                await search_return_policy(query="q", category="alimentacion")

        rpc_call_args = mock_client.rpc.call_args
        assert rpc_call_args[0][0] == "match_policy_embeddings"
        rpc_params = rpc_call_args[0][1]
        assert rpc_params["match_threshold"] == 0.5
        assert rpc_params["filter_category"] == "alimentacion"

    @pytest.mark.asyncio
    async def test_categoria_vacia_no_filtra_por_categoria_en_el_rpc(self):
        mock_client, query = _make_sync_supabase_client()
        query.execute = AsyncMock(return_value=MagicMock(data=[]))

        with patch(
            "backend.services.policy_service.get_policy_info",
            new=AsyncMock(return_value=None),
        ):
            p1, p2, p3, p4, _ = self._patched_env(mock_client)
            with p1, p2, p3, p4:
                await search_return_policy(query="q", category="")

        rpc_params = mock_client.rpc.call_args[0][1]
        assert rpc_params["filter_category"] is None

    @pytest.mark.asyncio
    async def test_llama_al_embedding_con_el_texto_de_la_query(self):
        mock_client, query = _make_sync_supabase_client()
        query.execute = AsyncMock(return_value=MagicMock(data=[]))

        with patch(
            "backend.services.policy_service.get_policy_info",
            new=AsyncMock(return_value=None),
        ):
            p1, p2, p3, p4, fake_openai_client = self._patched_env(mock_client)
            with p1, p2, p3, p4:
                await search_return_policy(
                    query="mi consulta de politica", category="juguetes"
                )

        embed_call_kwargs = fake_openai_client.embeddings.create.call_args.kwargs
        assert embed_call_kwargs["input"] == "mi consulta de politica"
        assert embed_call_kwargs["model"] == "text-embedding-3-small"
        assert "name" not in embed_call_kwargs
        assert "metadata" not in embed_call_kwargs

    @pytest.mark.asyncio
    async def test_usa_modelo_configurado_para_consultas(self):
        mock_client, query = _make_sync_supabase_client()
        query.execute = AsyncMock(return_value=MagicMock(data=[]))
        with patch(
            "backend.services.policy_service.get_policy_info",
            new=AsyncMock(return_value=None),
        ):
            p1, p2, p3, p4, fake_openai_client = self._patched_env(mock_client)
            with p1, p2, p3, p4 as settings_mock:
                settings_mock.return_value.rag_embedding_model = "modelo-de-prueba"
                await search_return_policy(query="q", category="calzado")
        assert fake_openai_client.embeddings.create.call_args.kwargs["model"] == (
            "modelo-de-prueba"
        )
