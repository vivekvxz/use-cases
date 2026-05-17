"""Configuration module for the Engineering Release Agent."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env and environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o-mini")
    use_ollama: bool = Field(default=False)
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="llama3.2")

    # GitHub
    github_token: str = Field(default="")
    github_webhook_secret: str = Field(default="dev_secret")

    # Jira
    jira_server: str = Field(default="")
    jira_email: str = Field(default="")
    jira_api_token: str = Field(default="")

    # Local storage
    chroma_persist_dir: str = Field(default="./data/chroma")
    sqlite_db_path: str = Field(default="./data/release_agent.db")

    # Agent
    agent_max_iterations: int = Field(default=10)
    hitl_risk_threshold: float = Field(default=0.75)
    confidence_threshold: float = Field(default=0.65)

    # Slack
    slack_bot_token: str = Field(default="")
    slack_channel_id: str = Field(default="")

    # App
    log_level: str = Field(default="INFO")
    environment: Literal["development", "staging", "production"] = Field(
        default="development"
    )
    internal_api_key: str = Field(default="dev-api-key")

    @computed_field
    @property
    def llm_provider(self) -> str:
        """Return the LLM provider name."""
        return "ollama" if self.use_ollama else "openai"

    @computed_field
    @property
    def slack_enabled(self) -> bool:
        """Check if Slack is configured."""
        return bool(self.slack_bot_token and self.slack_channel_id)

    @computed_field
    @property
    def jira_enabled(self) -> bool:
        """Check if Jira is configured."""
        return bool(self.jira_server and self.jira_email and self.jira_api_token)

    @computed_field
    @property
    def sqlite_url(self) -> str:
        """Return SQLAlchemy async connection URL for SQLite."""
        return f"sqlite+aiosqlite:///{self.sqlite_db_path}"

    @field_validator("hitl_risk_threshold", "confidence_threshold", mode="before")
    @classmethod
    def validate_threshold(cls, v: object) -> float:
        """Validate that thresholds are numeric values between 0.0 and 1.0."""
        try:
            value = float(v)
        except (TypeError, ValueError) as exc:
            raise ValueError("Threshold must be a number between 0.0 and 1.0") from exc

        if not 0.0 <= value <= 1.0:
            raise ValueError("Threshold must be between 0.0 and 1.0")
        return value

    @model_validator(mode="after")
    def validate_llm_config(self) -> Settings:
        """Validate that either OpenAI or Ollama is configured."""
        if not self.use_ollama and not self.openai_api_key:
            raise ValueError(
                "Set OPENAI_API_KEY in .env, or set USE_OLLAMA=true and run:\n"
                "  ollama pull llama3.2\n"
                "  ollama pull nomic-embed-text"
            )
        return self

    def ensure_data_dirs(self) -> None:
        """Create local data directories if they don't exist yet."""
        for d in [self.chroma_persist_dir, "./data/hitl", "./data/evals/reports"]:
            Path(d).mkdir(parents=True, exist_ok=True)
        Path(self.sqlite_db_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache()
def get_settings() -> Settings:
    """Return cached Settings singleton."""
    s = Settings()
    s.ensure_data_dirs()
    return s


def get_llm():
    """Return the appropriate LangChain chat model based on settings."""
    settings = get_settings()
    if settings.use_ollama:
        from langchain_community.chat_models import ChatOllama

        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=0,
        )
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )
