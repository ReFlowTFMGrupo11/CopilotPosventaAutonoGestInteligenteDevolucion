"""Tests unitarios de backend/services/observability.py.

El fixture autouse `_no_real_langfuse` (tests/conftest.py) desactiva
Langfuse (`get_langfuse` -> None) en TODA la suite, para no ensuciar
Langfuse real durante los tests -- efecto secundario: ninguna rama `if lf:`
de este módulo se ejercitaba nunca. Aquí se sobreescribe ese patch
localmente, dentro de cada test que necesita simular un cliente Langfuse
presente (el patch más interno gana mientras esté activo).

`get_langfuse()`/`get_langfuse_callback()` cachean en globals de módulo
(`_langfuse_instance`/`_callback_instance`/`_project_id`) -- un fixture
autouse los resetea antes/después de cada test.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.services import observability


@pytest.fixture(autouse=True)
def _no_real_langfuse():
    """Sobreescribe el fixture homónimo de tests/conftest.py (autouse a
    nivel de toda la suite, parchea justo `get_langfuse` a None) -- un
    fixture con el mismo nombre definido en el propio módulo de test tiene
    prioridad sobre el del conftest.py, así que este módulo, y solo este
    módulo, recupera el comportamiento real de get_langfuse() para poder
    probarlo. Sin esto, TODAS las llamadas a `observability.get_langfuse()`
    en este fichero devolverían None sin ejecutar nada del código real."""
    yield


@pytest.fixture(autouse=True)
def _reset_observability_globals():
    observability._langfuse_instance = None
    observability._callback_instance = None
    observability._project_id = None
    yield
    observability._langfuse_instance = None
    observability._callback_instance = None
    observability._project_id = None


def _fake_settings(**overrides):
    """SimpleNamespace con los campos de Settings que este módulo lee."""
    defaults = dict(
        langfuse_secret_key=None,
        langfuse_public_key=None,
        langfuse_base_url=None,
        langfuse_host=None,
        langfuse_project_id=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _secret(value: str):
    """Simula un pydantic.SecretStr con .get_secret_value()."""
    secret = MagicMock()
    secret.get_secret_value.return_value = value
    secret.__bool__ = lambda self: True
    return secret


class TestIsConfigured:
    def test_sin_ninguna_credencial_no_esta_configurado(self):
        settings = _fake_settings()
        with patch(
            "backend.services.observability.get_settings", return_value=settings
        ):
            assert observability._is_configured() is False

    def test_con_ambas_credenciales_esta_configurado(self):
        settings = _fake_settings(
            langfuse_secret_key=_secret("sk-1"), langfuse_public_key="pk-1"
        )
        with patch(
            "backend.services.observability.get_settings", return_value=settings
        ):
            assert observability._is_configured() is True

    def test_con_solo_una_credencial_no_esta_configurado(self):
        settings = _fake_settings(langfuse_public_key="pk-1")
        with patch(
            "backend.services.observability.get_settings", return_value=settings
        ):
            assert observability._is_configured() is False


class TestHost:
    def test_default_langfuse_cloud_sin_nada_configurado(self):
        settings = _fake_settings()
        with patch(
            "backend.services.observability.get_settings", return_value=settings
        ):
            assert observability._host() == "https://cloud.langfuse.com"

    def test_langfuse_base_url_tiene_prioridad(self):
        settings = _fake_settings(
            langfuse_base_url="https://mi-langfuse.com",
            langfuse_host="https://otro-host.com",
        )
        with patch(
            "backend.services.observability.get_settings", return_value=settings
        ):
            assert observability._host() == "https://mi-langfuse.com"

    def test_langfuse_host_como_fallback(self):
        settings = _fake_settings(langfuse_host="https://legacy-host.com")
        with patch(
            "backend.services.observability.get_settings", return_value=settings
        ):
            assert observability._host() == "https://legacy-host.com"


class TestGetLangfuse:
    def test_sin_credenciales_devuelve_none_sin_intentar_construir_cliente(self):
        settings = _fake_settings()
        with patch(
            "backend.services.observability.get_settings", return_value=settings
        ), patch("langfuse.Langfuse") as mock_cls:
            result = observability.get_langfuse()
        assert result is None
        mock_cls.assert_not_called()

    def test_configurado_construye_el_cliente_con_las_credenciales(self):
        settings = _fake_settings(
            langfuse_secret_key=_secret("sk-1"), langfuse_public_key="pk-1"
        )
        fake_client = MagicMock()
        with patch(
            "backend.services.observability.get_settings", return_value=settings
        ), patch("langfuse.Langfuse", return_value=fake_client) as mock_cls:
            result = observability.get_langfuse()

        assert result is fake_client
        mock_cls.assert_called_once_with(
            public_key="pk-1", secret_key="sk-1", host="https://cloud.langfuse.com"
        )

    def test_es_singleton_solo_construye_una_vez(self):
        settings = _fake_settings(
            langfuse_secret_key=_secret("sk-1"), langfuse_public_key="pk-1"
        )
        with patch(
            "backend.services.observability.get_settings", return_value=settings
        ), patch("langfuse.Langfuse") as mock_cls:
            first = observability.get_langfuse()
            second = observability.get_langfuse()

        assert first is second
        mock_cls.assert_called_once()

    def test_si_langfuse_lanza_excepcion_devuelve_none(self):
        settings = _fake_settings(
            langfuse_secret_key=_secret("sk-1"), langfuse_public_key="pk-1"
        )
        with patch(
            "backend.services.observability.get_settings", return_value=settings
        ), patch("langfuse.Langfuse", side_effect=Exception("conexión rechazada")):
            result = observability.get_langfuse()
        assert result is None


class TestWithLangfuse:
    def test_sin_langfuse_configurado_devuelve_config_sin_cambios(self):
        config = {"configurable": {"thread_id": "t1"}}
        with patch(
            "backend.services.observability.get_langfuse_callback", return_value=None
        ):
            result = observability.with_langfuse(config, thread_id="t1")
        assert result == config
        assert (
            result is config
        )  # no copia si no hay nada que añadir... o al menos misma info

    def test_con_callback_anade_callbacks_y_metadata(self):
        fake_callback = MagicMock()
        config = {"configurable": {"thread_id": "t1"}}
        with patch(
            "backend.services.observability.get_langfuse_callback",
            return_value=fake_callback,
        ):
            result = observability.with_langfuse(
                config,
                thread_id="thread-1",
                customer_id="cust-1",
                order_id="ord-1",
            )

        assert result["callbacks"] == [fake_callback]
        assert result["metadata"]["langfuse_session_id"] == "thread-1"
        assert result["metadata"]["langfuse_user_id"] == "cust-1"
        assert result["metadata"]["order_id"] == "ord-1"
        # El config original no se muta.
        assert "callbacks" not in config

    def test_preserva_callbacks_y_metadata_ya_existentes(self):
        fake_callback = MagicMock()
        otro_callback = MagicMock()
        config = {
            "callbacks": [otro_callback],
            "metadata": {"otra_clave": "otro_valor"},
        }
        with patch(
            "backend.services.observability.get_langfuse_callback",
            return_value=fake_callback,
        ):
            result = observability.with_langfuse(config, thread_id="thread-1")

        assert result["callbacks"] == [otro_callback, fake_callback]
        assert result["metadata"]["otra_clave"] == "otro_valor"
        assert result["metadata"]["langfuse_session_id"] == "thread-1"

    def test_sin_thread_id_ni_customer_id_ni_order_id_no_anade_metadata(self):
        fake_callback = MagicMock()
        config = {}
        with patch(
            "backend.services.observability.get_langfuse_callback",
            return_value=fake_callback,
        ):
            result = observability.with_langfuse(config)

        assert result["callbacks"] == [fake_callback]
        assert "metadata" not in result


class TestScoreRagSimilarity:
    def test_sin_thread_id_no_hace_nada(self):
        with patch("backend.services.observability.get_langfuse") as mock_get:
            observability.score_rag_similarity(None, "query", "categoria", [])
        mock_get.assert_not_called()

    def test_sin_langfuse_configurado_no_hace_nada(self):
        with patch("backend.services.observability.get_langfuse", return_value=None):
            # No debe lanzar ninguna excepción.
            observability.score_rag_similarity("thread-1", "query", "categoria", [])

    def test_con_resultados_registra_la_mejor_similitud(self):
        fake_lf = MagicMock()
        semantic_results = [
            {"chunk_text": "chunk peor", "similarity": 0.5},
            {"chunk_text": "chunk mejor", "similarity": 0.9},
        ]
        with patch("backend.services.observability.get_langfuse", return_value=fake_lf):
            observability.score_rag_similarity(
                "thread-1", "query", "cosmetica_perfumeria", semantic_results
            )

        fake_lf.create_score.assert_called_once()
        kwargs = fake_lf.create_score.call_args.kwargs
        assert kwargs["name"] == "rag_similarity"
        assert kwargs["value"] == 0.9
        assert kwargs["session_id"] == "thread-1"
        assert "chunk mejor" in kwargs["comment"]

    def test_sin_resultados_registra_value_cero(self):
        fake_lf = MagicMock()
        with patch("backend.services.observability.get_langfuse", return_value=fake_lf):
            observability.score_rag_similarity("thread-1", "query", "categoria", [])

        kwargs = fake_lf.create_score.call_args.kwargs
        assert kwargs["value"] == 0.0
        assert "chunks=0" in kwargs["comment"]

    def test_un_fallo_al_registrar_no_se_propaga(self):
        fake_lf = MagicMock()
        fake_lf.create_score.side_effect = Exception("Langfuse caído")
        with patch("backend.services.observability.get_langfuse", return_value=fake_lf):
            # No debe lanzar ninguna excepción.
            observability.score_rag_similarity("thread-1", "query", "categoria", [])


class TestScoreError:
    def test_sin_thread_id_no_hace_nada(self):
        with patch("backend.services.observability.get_langfuse") as mock_get:
            observability.score_error(None, "timeout")
        mock_get.assert_not_called()

    def test_con_thread_id_y_langfuse_registra_el_error(self):
        fake_lf = MagicMock()
        with patch("backend.services.observability.get_langfuse", return_value=fake_lf):
            observability.score_error("thread-1", "timeout")

        fake_lf.create_score.assert_called_once_with(
            name="error",
            value="timeout",
            session_id="thread-1",
            data_type="CATEGORICAL",
        )


class TestScoreResolution:
    def test_resolution_none_no_hace_nada(self):
        with patch("backend.services.observability.get_langfuse") as mock_get:
            observability.score_resolution("thread-1", None)
        mock_get.assert_not_called()

    def test_con_resolution_registra_el_score(self):
        fake_lf = MagicMock()
        with patch("backend.services.observability.get_langfuse", return_value=fake_lf):
            observability.score_resolution("thread-1", "approved")

        fake_lf.create_score.assert_called_once_with(
            name="resolution",
            value="approved",
            session_id="thread-1",
            data_type="CATEGORICAL",
        )


class TestScoreToolCall:
    def test_sin_thread_id_no_hace_nada(self):
        with patch("backend.services.observability.get_langfuse") as mock_get:
            observability.score_tool_call(None, "get_order_details", success=True)
        mock_get.assert_not_called()

    def test_sin_langfuse_configurado_no_hace_nada(self):
        with patch("backend.services.observability.get_langfuse", return_value=None):
            # No debe lanzar ninguna excepción.
            observability.score_tool_call("thread-1", "get_order_details", success=True)

    def test_exito_registra_value_success_con_el_tool_en_metadata(self):
        fake_lf = MagicMock()
        with patch("backend.services.observability.get_langfuse", return_value=fake_lf):
            observability.score_tool_call("thread-1", "get_order_details", success=True)

        fake_lf.create_score.assert_called_once_with(
            name="tool_call",
            value="success",
            session_id="thread-1",
            data_type="CATEGORICAL",
            metadata={"tool": "get_order_details"},
            comment=None,
        )

    def test_error_registra_value_error_con_el_mensaje_en_comment(self):
        fake_lf = MagicMock()
        with patch("backend.services.observability.get_langfuse", return_value=fake_lf):
            observability.score_tool_call(
                "thread-1",
                "create_return_record",
                success=False,
                error="constraint violada",
            )

        fake_lf.create_score.assert_called_once_with(
            name="tool_call",
            value="error",
            session_id="thread-1",
            data_type="CATEGORICAL",
            metadata={"tool": "create_return_record"},
            comment="constraint violada",
        )

    def test_un_fallo_al_registrar_no_se_propaga(self):
        fake_lf = MagicMock()
        fake_lf.create_score.side_effect = Exception("LangFuse caído")
        with patch("backend.services.observability.get_langfuse", return_value=fake_lf):
            # No debe lanzar ninguna excepción.
            observability.score_tool_call("thread-1", "get_order_details", success=True)


class TestResolveProjectId:
    def test_usa_el_override_de_settings_sin_llamar_a_la_api(self):
        settings = _fake_settings(langfuse_project_id="proj-fijo")
        with patch(
            "backend.services.observability.get_settings", return_value=settings
        ), patch("backend.services.observability.get_langfuse") as mock_get:
            result = observability._resolve_project_id()

        assert result == "proj-fijo"
        mock_get.assert_not_called()

    def test_sin_langfuse_devuelve_none(self):
        settings = _fake_settings()
        with patch(
            "backend.services.observability.get_settings", return_value=settings
        ), patch("backend.services.observability.get_langfuse", return_value=None):
            assert observability._resolve_project_id() is None

    def test_resuelve_el_primer_proyecto_de_la_api(self):
        settings = _fake_settings()
        fake_lf = MagicMock()
        fake_lf.api.projects.get.return_value = SimpleNamespace(
            data=[SimpleNamespace(id="proj-abc")]
        )
        with patch(
            "backend.services.observability.get_settings", return_value=settings
        ), patch("backend.services.observability.get_langfuse", return_value=fake_lf):
            result = observability._resolve_project_id()

        assert result == "proj-abc"

    def test_cachea_el_resultado_no_llama_dos_veces_a_la_api(self):
        settings = _fake_settings()
        fake_lf = MagicMock()
        fake_lf.api.projects.get.return_value = SimpleNamespace(
            data=[SimpleNamespace(id="proj-abc")]
        )
        with patch(
            "backend.services.observability.get_settings", return_value=settings
        ), patch("backend.services.observability.get_langfuse", return_value=fake_lf):
            observability._resolve_project_id()
            observability._resolve_project_id()

        fake_lf.api.projects.get.assert_called_once()

    def test_si_la_api_falla_devuelve_none(self):
        settings = _fake_settings()
        fake_lf = MagicMock()
        fake_lf.api.projects.get.side_effect = Exception("timeout")
        with patch(
            "backend.services.observability.get_settings", return_value=settings
        ), patch("backend.services.observability.get_langfuse", return_value=fake_lf):
            assert observability._resolve_project_id() is None


class TestLangfuseLinks:
    def test_no_configurado(self):
        with patch("backend.services.observability._is_configured", return_value=False):
            assert observability.get_langfuse_links() == {"configured": False}

    def test_configurado_sin_project_id_resuelto(self):
        with patch(
            "backend.services.observability._is_configured", return_value=True
        ), patch(
            "backend.services.observability._host",
            return_value="https://cloud.langfuse.com",
        ), patch(
            "backend.services.observability._resolve_project_id", return_value=None
        ):
            result = observability.get_langfuse_links()

        assert result == {
            "configured": True,
            "host": "https://cloud.langfuse.com",
            "sessions_url": None,
            "users_url": None,
        }

    def test_configurado_con_project_id_construye_las_urls(self):
        with patch(
            "backend.services.observability._is_configured", return_value=True
        ), patch(
            "backend.services.observability._host",
            return_value="https://cloud.langfuse.com",
        ), patch(
            "backend.services.observability._resolve_project_id",
            return_value="proj-abc",
        ):
            result = observability.get_langfuse_links()

        assert (
            result["sessions_url"]
            == "https://cloud.langfuse.com/project/proj-abc/sessions"
        )
        assert (
            result["users_url"] == "https://cloud.langfuse.com/project/proj-abc/users"
        )


class TestFlush:
    def test_sin_langfuse_no_hace_nada(self):
        with patch("backend.services.observability.get_langfuse", return_value=None):
            observability.flush()  # no debe lanzar

    def test_con_langfuse_llama_a_flush(self):
        fake_lf = MagicMock()
        with patch("backend.services.observability.get_langfuse", return_value=fake_lf):
            observability.flush()
        fake_lf.flush.assert_called_once()

    def test_un_fallo_en_flush_no_se_propaga(self):
        fake_lf = MagicMock()
        fake_lf.flush.side_effect = Exception("red caída")
        with patch("backend.services.observability.get_langfuse", return_value=fake_lf):
            observability.flush()  # no debe lanzar
