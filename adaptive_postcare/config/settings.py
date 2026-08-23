"""
Environment and agent settings management.
"""

from functools import lru_cache
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    """
    Application configuration for the agent layer.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # LLM Settings
    llm_provider: str = Field(default="groq", description="LLM provider: groq, ollama, openai, vllm")
    llm_model: str = Field(default="llama-3.3-70b-versatile", description="Model name")
    llm_base_url: Optional[str] = Field(default=None, description="Custom base URL for OpenAI-compatible or Ollama endpoint")
    llm_api_key: Optional[str] = Field(default=None, description="API key for cloud inference providers")
    llm_temperature: float = Field(default=0.2, description="Sampling temperature")

    # Operational defaults
    max_retry_attempts: int = Field(default=3, description="Max retry attempts for LLM structured outputs")
    default_care_duration_days: int = Field(default=30, description="Default monitoring window in days")


@lru_cache()
def get_settings() -> AgentSettings:
    """Return cached instance of AgentSettings."""
    return AgentSettings()
