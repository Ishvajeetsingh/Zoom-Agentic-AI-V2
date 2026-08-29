from __future__ import annotations

from app.core.config import Settings, settings
from app.integrations.groq.client import GroqApiClient
from app.integrations.ollama.client import OllamaApiClient


def create_llm_client(
    config: Settings = settings,
):
    provider = (
        config.llm_provider
        .lower()
        .strip()
    )

    if provider == "groq":
        return GroqApiClient(
            config=config
        )

    if provider == "ollama":
        return OllamaApiClient(
            config=config
        )

    raise ValueError(
        "Unsupported LLM_PROVIDER: "
        f"{config.llm_provider}"
    )


def get_generation_model(
    config: Settings = settings,
) -> str:
    if (
        config.llm_provider
        .lower()
        .strip()
        == "groq"
    ):
        return config.groq_model

    return config.ollama_primary_model