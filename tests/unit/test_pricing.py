"""Tests unitarios de backend/services/pricing.py.

Depende de Settings (backend/config.py) para los overrides de precio
(LLM_PRICES_JSON) y tipo de cambio (USD_TO_EUR_RATE) -- ver
docs/REMAINING_TASKS.md §2, paso 2. get_settings() está cacheado con
@lru_cache: sin limpiar la cache antes/después de cada test que cambie
estas env vars, el override de monkeypatch no tendría ningún efecto (mismo
patrón que tests/unit/test_llm_factory.py).

Usa monkeypatch (no os.environ directo) para que cada test quede aislado
sin ensuciar variables de entorno entre tests.
"""

import pytest

from backend.config import get_settings
from backend.services import pricing


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestPricePerMillionUsd:
    def test_modelo_conocido_devuelve_precio_por_defecto(self, monkeypatch):
        monkeypatch.delenv("LLM_PRICES_JSON", raising=False)
        assert pricing.get_price_per_million_usd("gpt-5-mini") == (0.25, 2.00)
        assert pricing.get_price_per_million_usd("gpt-5-nano") == (0.05, 0.40)

    def test_modelo_desconocido_sin_override_devuelve_none(self, monkeypatch):
        monkeypatch.delenv("LLM_PRICES_JSON", raising=False)
        assert pricing.get_price_per_million_usd("gpt-9-ultra") is None

    def test_llm_prices_json_sobreescribe_precio_de_modelo_conocido(
        self, monkeypatch
    ):
        monkeypatch.setenv("LLM_PRICES_JSON", '{"gpt-5-mini": [1.5, 3.0]}')
        assert pricing.get_price_per_million_usd("gpt-5-mini") == (1.5, 3.0)

    def test_llm_prices_json_da_de_alta_modelo_no_listado(self, monkeypatch):
        monkeypatch.setenv("LLM_PRICES_JSON", '{"gpt-9-ultra": [10.0, 20.0]}')
        assert pricing.get_price_per_million_usd("gpt-9-ultra") == (10.0, 20.0)

    def test_llm_prices_json_puede_traer_varios_modelos_a_la_vez(
        self, monkeypatch
    ):
        monkeypatch.setenv(
            "LLM_PRICES_JSON",
            '{"gpt-5-mini": [1.5, 3.0], "gpt-9-ultra": [10.0, 20.0]}',
        )
        assert pricing.get_price_per_million_usd("gpt-5-mini") == (1.5, 3.0)
        assert pricing.get_price_per_million_usd("gpt-9-ultra") == (10.0, 20.0)
        # Un modelo con default y sin override en el JSON sigue cayendo al
        # default -- el override es por modelo, no sustituye todo el dict.
        assert pricing.get_price_per_million_usd("gpt-5-nano") == (0.05, 0.40)


class TestUsdToEurRate:
    def test_default_sin_env_var(self, monkeypatch):
        monkeypatch.delenv("USD_TO_EUR_RATE", raising=False)
        assert pricing.get_usd_to_eur_rate() == 0.86

    def test_env_var_sobreescribe_el_tipo_de_cambio(self, monkeypatch):
        monkeypatch.setenv("USD_TO_EUR_RATE", "0.90")
        assert pricing.get_usd_to_eur_rate() == 0.90


class TestEstimateCostEur:
    def test_modelo_desconocido_devuelve_none(self, monkeypatch):
        monkeypatch.delenv("LLM_PRICES_JSON", raising=False)
        assert pricing.estimate_cost_eur("gpt-9-ultra", 1000, 500) is None

    def test_cero_tokens_devuelve_cero(self, monkeypatch):
        monkeypatch.delenv("USD_TO_EUR_RATE", raising=False)
        assert pricing.estimate_cost_eur("gpt-5-mini", 0, 0) == 0.0

    def test_calculo_exacto_con_tipo_de_cambio_fijo(self, monkeypatch):
        """1M tokens de entrada + 1M de salida de gpt-5-mini a un tipo de
        cambio fijo de 1.0 USD->EUR debe dar exactamente input_price +
        output_price en euros (0.25 + 2.00 = 2.25)."""
        monkeypatch.setenv("USD_TO_EUR_RATE", "1.0")
        cost = pricing.estimate_cost_eur("gpt-5-mini", 1_000_000, 1_000_000)
        assert cost == pytest.approx(2.25)

    def test_aplica_el_tipo_de_cambio(self, monkeypatch):
        monkeypatch.setenv("USD_TO_EUR_RATE", "0.5")
        cost = pricing.estimate_cost_eur("gpt-5-mini", 1_000_000, 0)
        # 0.25 USD * 0.5 = 0.125 EUR
        assert cost == pytest.approx(0.125)

    def test_solo_tokens_de_entrada(self, monkeypatch):
        monkeypatch.setenv("USD_TO_EUR_RATE", "1.0")
        cost = pricing.estimate_cost_eur("gpt-5-nano", 2_000_000, 0)
        # 2M tokens de entrada * 0.05$/1M = 0.10 USD
        assert cost == pytest.approx(0.10)

    def test_solo_tokens_de_salida(self, monkeypatch):
        monkeypatch.setenv("USD_TO_EUR_RATE", "1.0")
        cost = pricing.estimate_cost_eur("gpt-5-nano", 0, 500_000)
        # 0.5M tokens de salida * 0.40$/1M = 0.20 USD
        assert cost == pytest.approx(0.20)


class TestConfiguredModelsMissingPrice:
    """`Settings` (modelo por nodo) y `pricing.py` (precio por modelo) son
    dos fuentes de verdad independientes -- estos tests cubren la validación
    que las cruza (ver docstring de `configured_models_missing_price`).
    El fixture `_clear_settings_cache` ya limpia la cache antes/después de
    cada test; aquí solo hace falta fijar las env vars."""

    def test_configuracion_por_defecto_no_tiene_modelos_sin_precio(
        self, monkeypatch
    ):
        """Los tres nodos caen a "gpt-5-mini" por defecto (ver config.py),
        que sí tiene precio en _DEFAULT_PRICES_USD_PER_MILLION."""
        monkeypatch.delenv("TRIAGE_MODEL", raising=False)
        monkeypatch.delenv("EVALUATOR_MODEL", raising=False)
        monkeypatch.delenv("RESOLVER_MODEL", raising=False)
        monkeypatch.delenv("LLM_PRICES_JSON", raising=False)

        assert pricing.configured_models_missing_price() == []

    def test_detecta_un_modelo_configurado_sin_precio_conocido(self, monkeypatch):
        monkeypatch.setenv("TRIAGE_MODEL", "gpt-9-ultra")
        monkeypatch.delenv("LLM_PRICES_JSON", raising=False)

        assert pricing.configured_models_missing_price() == ["gpt-9-ultra"]

    def test_un_override_en_llm_prices_json_cuenta_como_precio_conocido(
        self, monkeypatch
    ):
        monkeypatch.setenv("TRIAGE_MODEL", "gpt-9-ultra")
        monkeypatch.setenv("LLM_PRICES_JSON", '{"gpt-9-ultra": [10.0, 20.0]}')

        assert pricing.configured_models_missing_price() == []
