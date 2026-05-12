"""Typed application settings loaded from environment variables.

All configuration lives here. Routes and services should call
``get_settings()`` rather than reading os.environ directly.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- App ---------------------------------------------------------------
    env: str = Field(default="development", alias="LIBRA_ENV")
    log_level: str = Field(default="info", alias="LIBRA_LOG_LEVEL")
    api_host: str = Field(default="0.0.0.0", alias="LIBRA_API_HOST")
    api_port: int = Field(default=8000, alias="LIBRA_API_PORT")
    cors_origins: str = Field(
        default="http://localhost:3000",
        alias="LIBRA_CORS_ORIGINS",
        description="Comma-separated list of allowed CORS origins.",
    )

    # ---- OpenAI Realtime ---------------------------------------------------
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_realtime_model: str = Field(
        default="gpt-realtime", alias="OPENAI_REALTIME_MODEL"
    )
    openai_realtime_voice: str = Field(default="alloy", alias="OPENAI_REALTIME_VOICE")

    # ---- ElevenLabs + OpenAI reasoning -------------------------------------
    elevenlabs_api_key: str | None = Field(default=None, alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str | None = Field(default=None, alias="ELEVENLABS_VOICE_ID")
    elevenlabs_model_id: str = Field(
        default="eleven_flash_v2_5", alias="ELEVENLABS_MODEL_ID"
    )
    openai_reasoning_model: str = Field(
        default="gpt-4.1-mini", alias="OPENAI_REASONING_MODEL"
    )
    openai_transcription_model: str = Field(
        default="gpt-4o-mini-transcribe", alias="OPENAI_TRANSCRIPTION_MODEL"
    )

    # ---- Infrastructure ----------------------------------------------------
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    redis_url: str | None = Field(default=None, alias="REDIS_URL")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
