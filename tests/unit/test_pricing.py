"""Tests unitarios de backend/services/pricing.py.

Código puro (sin I/O, sin red) -- el candidato más barato y de mayor valor
para cerrar el hueco de cobertura detectado en tests/qa/*: la aritmética
de coste que alimenta la pestaña de Costes (frontend/pages/2_Costes.py,
vía usage_service.py) no tenía ningún test dedicado.

Usa monkeypatch (no os.environ directo) para que cada test quede aislado
sin ensuciar variables de entorno entre tests.
"""

import pytest

from backend.services import pricing


class TestEnvKey:
    def test_normaliza_guiones_a_guion_bajo(self):
        assert pricing._env_key("gpt-5-mini") == "GPT_5_MINI"

    def test_normaliza_puntos_a_guion_bajo(self):
        assert pricing._env_key("gpt-4.1") == "GPT_4_1"

    def test_pone_en_mayusculas(self):
        assert pricing._env_key("gpt-5-nano") == "GPT_5_NANO"


class TestPricePerMillionUsd:
    def test_modelo_conocido_devuelve_precio_por_defecto(self):
        assert pricing.price_per_million_usd("gpt-5-mini") == (0.25, 2.00)
        assert pricing.price_per_million_usd("gpt-5-nano") == (0.05, 0.40)

    def test_modelo_desconocido_sin_env_devuelve_none(self, monkeypatch):
        monkeypatch.delenv("LLM_PRICE_GPT_9_ULTRA_INPUT_PER_1M", raising=False)
        monkeypatch.delenv("LLM_PRICE_GPT_9_ULTRA_OUTPUT_PER_1M", raising=False)
        assert pricing.price_per_million_usd("gpt-9-ultra") is None

    def test_env_var_sobreescribe_precio_de_modelo_conocido(self, monkeypatch):
        monkeypatch.setenv("LLM_PRICE_GPT_5_MINI_INPUT_PER_1M", "1.5")
        monkeypatch.setenv("LLM_PRICE_GPT_5_MINI_OUTPUT_PER_1M", "3.0")
        assert pricing.price_per_million_usd("gpt-5-mini") == (1.5, 3.0)

    def test_env_var_da_de_alta_modelo_no_listado(self, monkeypatch):
        monkeypatch.setenv("LLM_PRICE_GPT_9_ULTRA_INPUT_PER_1M", "10.0")
        monkeypatch.setenv("LLM_PRICE_GPT_9_ULTRA_OUTPUT_PER_1M", "20.0")
        assert pricing.price_per_million_usd("gpt-9-ultra") == (10.0, 20.0)

    def test_solo_una_env_var_fijada_cae_al_default_no_falla(self, monkeypatch):
        """Documenta el comportamiento real: deben fijarse las DOS env vars o
        ninguna -- fijar solo una no es un error, simplemente se ignora y se
        usa el default (o None si el modelo no tiene default)."""
        monkeypatch.setenv("LLM_PRICE_GPT_5_MINI_INPUT_PER_1M", "1.5")
        monkeypatch.delenv("LLM_PRICE_GPT_5_MINI_OUTPUT_PER_1M", raising=False)
        assert pricing.price_per_million_usd("gpt-5-mini") == (0.25, 2.00)


class TestUsdToEurRate:
    def test_default_sin_env_var(self, monkeypatch):
        monkeypatch.delenv("USD_TO_EUR_RATE", raising=False)
        assert pricing.usd_to_eur_rate() == 0.86

    def test_env_var_sobreescribe_el_tipo_de_cambio(self, monkeypatch):
        monkeypatch.setenv("USD_TO_EUR_RATE", "0.90")
        assert pricing.usd_to_eur_rate() == 0.90


class TestEstimateCostEur:
    def test_modelo_desconocido_devuelve_none(self, monkeypatch):
        monkeypatch.delenv("LLM_PRICE_GPT_9_ULTRA_INPUT_PER_1M", raising=False)
        monkeypatch.delenv("LLM_PRICE_GPT_9_ULTRA_OUTPUT_PER_1M", raising=False)
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
