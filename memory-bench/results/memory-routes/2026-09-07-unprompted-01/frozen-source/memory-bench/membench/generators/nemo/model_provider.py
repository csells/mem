"""Point NeMo Data Designer at a LOCAL NIM (no paid API).

A local NIM exposes an OpenAI-compatible endpoint (default
``http://localhost:8000/v1``); Data Designer reaches it through a
``ModelProvider`` (``provider_type='openai'``) plus a ``ModelConfig`` mapping a
``model_alias`` to a served model. These helpers build that pair so the world
generator's text columns resolve to the local NIM and never call a hosted API —
mem's no-paid-API stance (the memory stack stays free; generation is offline).

The ``data_designer`` SDK is imported inside the functions, so this module loads
without it (CI never imports NeMo). Return types are loose (``Any``) for the same
reason. To run against a NIM: start the container (see the smoke bead), then call
``generate_world_records`` — it defaults to these helpers.
"""

from __future__ import annotations

from typing import Any

from membench.generators.nemo.column_spec import DEFAULT_MODEL_ALIAS

# A local NIM's default OpenAI-compatible base URL and a common served model.
# Both are overridable; the model id must match whatever the running NIM serves.
DEFAULT_NIM_ENDPOINT = "http://localhost:8000/v1"
DEFAULT_NIM_MODEL = "meta/llama-3.1-8b-instruct"
DEFAULT_NIM_PROVIDER_NAME = "local-nim"


def local_nim_provider(*, endpoint: str = DEFAULT_NIM_ENDPOINT, api_key: str | None = None) -> Any:
    """A ``ModelProvider`` pointing at a local NIM's OpenAI-compatible endpoint. A
    local NIM needs no key; ``api_key`` is accepted for endpoints that gate on a
    placeholder token."""
    from data_designer.config import ModelProvider  # lazy

    return ModelProvider(
        name=DEFAULT_NIM_PROVIDER_NAME,
        endpoint=endpoint,
        provider_type="openai",
        api_key=api_key,
    )


def local_nim_model_config(
    *, alias: str = DEFAULT_MODEL_ALIAS, model: str = DEFAULT_NIM_MODEL
) -> Any:
    """A ``ModelConfig`` binding the column spec's ``model_alias`` to a model served
    by the local NIM provider."""
    from data_designer.config import ModelConfig  # lazy

    return ModelConfig(alias=alias, model=model, provider=DEFAULT_NIM_PROVIDER_NAME)
