"""
Precios de LLM y tipo de cambio, para estimar el coste en euros del uso
registrado en ``llm_usage`` (ver usage_service.py / usage_tracking.py).

Son APROXIMADOS: OpenAI no expone los precios vía API, así que hay que
fijarlos a mano aquí y mantenerlos al día si cambian, o sobreescribirlos
por env var sin tocar código.

Precios por defecto (USD por millón de tokens, tier estándar no-batch),
consultados el 2026-08-28:
    gpt-5-nano: $0.05 entrada / $0.40 salida
    gpt-5-mini: $0.25 entrada / $2.00 salida

Tipo de cambio USD→EUR por defecto: 0.86 (aprox. a la misma fecha).
"""

from __future__ import annotations

import os

# (input $/1M tokens, output $/1M tokens)
_DEFAULT_PRICES_USD_PER_MILLION: dict[str, tuple[float, float]] = {
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5-mini": (0.25, 2.00),
}


def _env_key(model: str) -> str:
    return model.upper().replace("-", "_").replace(".", "_")


def price_per_million_usd(model: str) -> tuple[float, float] | None:
    """(input, output) en $/1M tokens para ``model``, o None si no se conoce.

    Se puede fijar/sobreescribir vía env vars
    ``LLM_PRICE_{MODEL}_INPUT_PER_1M`` / ``LLM_PRICE_{MODEL}_OUTPUT_PER_1M``
    (p. ej. ``LLM_PRICE_GPT_5_MINI_INPUT_PER_1M``), tanto para corregir un
    precio desactualizado como para dar de alta un modelo no listado en
    ``_DEFAULT_PRICES_USD_PER_MILLION``. Deben fijarse ambas o ninguna.
    """
    key = _env_key(model)
    input_env = os.getenv(f"LLM_PRICE_{key}_INPUT_PER_1M")
    output_env = os.getenv(f"LLM_PRICE_{key}_OUTPUT_PER_1M")
    if input_env is not None and output_env is not None:
        return float(input_env), float(output_env)
    return _DEFAULT_PRICES_USD_PER_MILLION.get(model)


def usd_to_eur_rate() -> float:
    return float(os.getenv("USD_TO_EUR_RATE", "0.86"))


def estimate_cost_eur(
    model: str, input_tokens: int, output_tokens: int
) -> float | None:
    """Coste estimado en euros de una llamada, o None si no se conoce el
    precio de ``model`` (ni por defecto ni por env var)."""
    prices = price_per_million_usd(model)
    if prices is None:
        return None
    input_price, output_price = prices
    cost_usd = (input_tokens / 1_000_000) * input_price + (
        output_tokens / 1_000_000
    ) * output_price
    return cost_usd * usd_to_eur_rate()
