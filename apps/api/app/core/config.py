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

    # ---- Memory (v0.2) -----------------------------------------------------
    openai_embedding_model: str = Field(
        default="text-embedding-3-small", alias="OPENAI_EMBEDDING_MODEL"
    )
    embedding_dim: int = Field(default=1536, alias="LIBRA_EMBEDDING_DIM")
    memory_short_term_max_turns: int = Field(
        default=40, alias="LIBRA_MEMORY_SHORT_TERM_MAX_TURNS"
    )
    memory_recall_top_k: int = Field(
        default=5, alias="LIBRA_MEMORY_RECALL_TOP_K"
    )
    memory_default_user_id: str = Field(
        default="default", alias="LIBRA_MEMORY_DEFAULT_USER_ID"
    )
    memory_distill_model: str = Field(
        default="gpt-4.1-mini", alias="LIBRA_MEMORY_DISTILL_MODEL"
    )

    # ---- Tools (v0.3) ------------------------------------------------------
    tools_enabled: bool = Field(default=True, alias="LIBRA_TOOLS_ENABLED")
    tools_max_iterations: int = Field(
        default=5,
        alias="LIBRA_TOOLS_MAX_ITERATIONS",
        description="Max tool-loop rounds per user turn before giving up.",
    )
    web_search_enabled: bool = Field(
        default=True,
        alias="LIBRA_WEB_SEARCH_ENABLED",
        description="Enable OpenAI's built-in web_search Responses tool.",
    )

    # ---- Spotify integration (v0.3) ----------------------------------------
    spotify_client_id: str | None = Field(default=None, alias="SPOTIFY_CLIENT_ID")
    spotify_client_secret: str | None = Field(
        default=None, alias="SPOTIFY_CLIENT_SECRET"
    )
    spotify_redirect_uri: str = Field(
        default="http://127.0.0.1:8000/api/integrations/spotify/auth/callback",
        alias="SPOTIFY_REDIRECT_URI",
    )
    spotify_post_auth_redirect: str = Field(
        default="http://localhost:3000/?spotify=connected",
        alias="SPOTIFY_POST_AUTH_REDIRECT",
        description="Where to bounce the browser after a successful Spotify "
        "OAuth callback. Typically the Libra UI origin.",
    )

    # ---- Vision / MQTT (v0.4) ----------------------------------------------
    vision_enabled: bool = Field(default=True, alias="LIBRA_VISION_ENABLED")
    mqtt_host: str = Field(default="mosquitto", alias="LIBRA_MQTT_HOST")
    mqtt_port: int = Field(default=1883, alias="LIBRA_MQTT_PORT")
    mqtt_username: str = Field(default="", alias="LIBRA_MQTT_USERNAME")
    mqtt_password: str = Field(default="", alias="LIBRA_MQTT_PASSWORD")
    vision_topic_filter: str = Field(
        default="libra/vision/+/detections", alias="LIBRA_VISION_TOPIC_FILTER"
    )
    vision_status_topic_filter: str = Field(
        default="libra/vision/+/status", alias="LIBRA_VISION_STATUS_TOPIC_FILTER"
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
