"""
Precios de LLM y tipo de cambio, para estimar el coste en euros del uso
registrado en ``llm_usage`` (ver usage_service.py / usage_tracking.py).

Son APROXIMADOS: OpenAI no expone los precios vía API, así que hay que
fijarlos a mano aquí y mantenerlos al día si cambian, o sobreescribirlos vía
``Settings`` (``LLM_PRICES_JSON``/``USD_TO_EUR_RATE``, ver
``backend/config.py``) sin tocar código.

Precios por defecto (USD por millón de tokens, tier estándar no-batch),
consultados el 2026-08-28:
    gpt-5-nano: $0.05 entrada / $0.40 salida
    gpt-5-mini: $0.25 entrada / $2.00 salida

Tipo de cambio USD→EUR por defecto: 0.86 (aprox. a la misma fecha).
"""

from __future__ import annotations

from backend.config import get_settings

# (input $/1M tokens, output $/1M tokens)
_DEFAULT_PRICES_USD_PER_MILLION: dict[str, tuple[float, float]] = {
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5-mini": (0.25, 2.00),
}


def get_price_per_million_usd(model: str) -> tuple[float, float] | None:
    """(input, output) en $/1M tokens para ``model``, o None si no se conoce.

    Se puede fijar/sobreescribir vía ``Settings.llm_prices_json``
    (env var ``LLM_PRICES_JSON``, un único JSON con todos los overrides —
    ver ``backend/config.py``), tanto para corregir un precio desactualizado
    como para dar de alta un modelo no listado en
    ``_DEFAULT_PRICES_USD_PER_MILLION``. No hace falta listar los dos precios
    de un modelo si no se quiere sobreescribir: el override sustituye la
    entrada entera de ese modelo, no se combina campo a campo con el default.
    """
    overrides = get_settings().llm_prices_json
    if model in overrides:
        return overrides[model]
    return _DEFAULT_PRICES_USD_PER_MILLION.get(model)


def get_usd_to_eur_rate() -> float:
    """Tipo de cambio USD→EUR: ``Settings.usd_to_eur_rate``
    (env var ``USD_TO_EUR_RATE``) o el default aproximado (0.86)."""
    return get_settings().usd_to_eur_rate


def estimate_cost_eur(
    model: str, input_tokens: int, output_tokens: int
) -> float | None:
    """Coste estimado en euros de una llamada, o None si no se conoce el
    precio de ``model`` (ni por defecto ni por env var)."""
    prices = get_price_per_million_usd(model)
    if prices is None:
        return None
    input_price, output_price = prices
    cost_usd = (input_tokens / 1_000_000) * input_price + (
        output_tokens / 1_000_000
    ) * output_price
    return cost_usd * get_usd_to_eur_rate()


def configured_models_missing_price() -> list[str]:
    """Modelos configurados en ``Settings`` (``triage_model``,
    ``evaluator_model``, ``resolver_model``) que no tienen precio conocido
    aquí, ni por defecto ni por override en ``llm_prices_json``.

    Antes de esto, quién decide qué modelo usa cada nodo (``Settings``) y
    quién sabe cuánto cuesta ese modelo (este fichero) no se validaban entre
    sí. Si se cambia ``TRIAGE_MODEL``/``EVALUATOR_MODEL``/``RESOLVER_MODEL``
    a un modelo sin entrada aquí (y sin darlo de alta en
    ``LLM_PRICES_JSON``), ese nodo empieza a generar filas de ``llm_usage``
    con ``cost_eur=None`` en silencio, sin aviso, y el dashboard de costes
    las marca como "incompleto" sin que nadie sepa por qué. Se usa en el
    arranque de la API (``backend/api/main.py::lifespan``) para loguear un
    warning temprano en vez de descubrirlo al mirar el dashboard.
    """
    settings = get_settings()
    configured = {
        settings.triage_model,
        settings.evaluator_model,
        settings.resolver_model,
    }
    return sorted(
        model for model in configured if get_price_per_million_usd(model) is None
    )
