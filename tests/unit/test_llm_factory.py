"""Tests unitarios de backend/agents/llm_factory.py.

get_settings() está cacheado con @lru_cache (backend/config.py) -- hay que
limpiar la cache antes/después de cada test que cambie env vars, si no el
override de monkeypatch no tiene ningún efecto (la Settings ya construida
se sigue reutilizando).

No mockea ChatOpenAI: construirlo no hace ninguna llamada de red (solo
guarda configuración), así que se verifica el objeto real devuelto. Se fija
un OPENAI_API_KEY dummy vía monkeypatch para no depender de que haya un
.env real con credenciales en el entorno que ejecute los tests (CI).
"""

import pytest

from backend.agents.llm_factory import build_chat_llm, trim_history
from backend.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache(monkeypatch):
    """Limpia la cache de get_settings() antes y después de cada test, y
    fija un OPENAI_API_KEY dummy para que ChatOpenAI() no dependa del
    entorno real."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestBuildChatLlm:
    def test_usa_el_modelo_por_defecto_si_no_hay_env_var(self, monkeypatch):
        monkeypatch.delenv("TRIAGE_MODEL", raising=False)
        llm = build_chat_llm("TRIAGE_MODEL", temperature=0.0)
        assert llm.model_name == "gpt-5-mini"

    def test_lee_el_modelo_desde_env_var(self, monkeypatch):
        monkeypatch.setenv("TRIAGE_MODEL", "gpt-5-nano")
        llm = build_chat_llm("TRIAGE_MODEL", temperature=0.0)
        assert llm.model_name == "gpt-5-nano"

    def test_quita_el_prefijo_openai_del_nombre_del_modelo(self, monkeypatch):
        monkeypatch.setenv("TRIAGE_MODEL", "openai:gpt-5-mini")
        llm = build_chat_llm("TRIAGE_MODEL", temperature=0.0)
        assert llm.model_name == "gpt-5-mini"

    def test_usa_la_temperatura_pasada_por_argumento_si_no_hay_override(
        self, monkeypatch
    ):
        # gpt-5-mini (familia "reasoning") ignora `temperature` en
        # ChatOpenAI -- se usa gpt-4o-mini aquí para aislar la lógica de
        # resolución de build_chat_llm() de esa particularidad del modelo,
        # no relacionada con lo que este test verifica.
        monkeypatch.setenv("EVALUATOR_MODEL", "gpt-4o-mini")
        monkeypatch.delenv("EVALUATOR_MODEL_TEMPERATURE", raising=False)
        llm = build_chat_llm("EVALUATOR_MODEL", temperature=0.3)
        assert llm.temperature == 0.3

    def test_env_var_de_temperatura_sobreescribe_el_argumento(self, monkeypatch):
        monkeypatch.setenv("EVALUATOR_MODEL", "gpt-4o-mini")
        monkeypatch.setenv("EVALUATOR_MODEL_TEMPERATURE", "0.7")
        llm = build_chat_llm("EVALUATOR_MODEL", temperature=0.0)
        assert llm.temperature == 0.7

    def test_usa_max_tokens_global_por_defecto(self, monkeypatch):
        monkeypatch.delenv("RESOLVER_MODEL_MAX_TOKENS", raising=False)
        monkeypatch.delenv("LLM_MAX_OUTPUT_TOKENS", raising=False)
        llm = build_chat_llm("RESOLVER_MODEL", temperature=0.0)
        assert llm.max_tokens == 4096

    def test_max_tokens_pasado_por_argumento_gana_al_global(self, monkeypatch):
        monkeypatch.delenv("RESOLVER_MODEL_MAX_TOKENS", raising=False)
        llm = build_chat_llm("RESOLVER_MODEL", temperature=0.0, max_tokens=1024)
        assert llm.max_tokens == 1024

    def test_env_var_de_max_tokens_especifica_del_nodo_gana_a_todo(self, monkeypatch):
        monkeypatch.setenv("RESOLVER_MODEL_MAX_TOKENS", "2048")
        llm = build_chat_llm("RESOLVER_MODEL", temperature=0.0, max_tokens=1024)
        assert llm.max_tokens == 2048

    def test_usa_el_timeout_configurado(self, monkeypatch):
        monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "30")
        llm = build_chat_llm("TRIAGE_MODEL", temperature=0.0)
        assert llm.request_timeout == 30.0


class TestTrimHistory:
    def test_no_recorta_si_hay_menos_mensajes_que_el_limite(self):
        messages = list(range(5))
        assert trim_history(messages, max_messages=20) == messages

    def test_recorta_a_los_ultimos_n_mensajes(self):
        messages = list(range(30))
        result = trim_history(messages, max_messages=10)
        assert result == list(range(20, 30))
        assert len(result) == 10

    def test_limite_cero_o_negativo_no_recorta(self):
        messages = list(range(30))
        assert trim_history(messages, max_messages=0) == messages
        assert trim_history(messages, max_messages=-5) == messages

    def test_usa_max_history_messages_de_settings_por_defecto(self, monkeypatch):
        monkeypatch.setenv("MAX_HISTORY_MESSAGES", "3")
        messages = list(range(10))
        result = trim_history(messages)
        assert result == [7, 8, 9]

    def test_lista_vacia_devuelve_lista_vacia(self):
        assert trim_history([], max_messages=10) == []
