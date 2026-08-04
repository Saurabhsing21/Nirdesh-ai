import os
from functools import cached_property
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    sarvam_api_key: SecretStr | None = None
    sarvam_chat_base_url: str = "https://api.sarvam.ai/v1"
    exa_api_key: SecretStr | None = None
    exa_search_timeout_seconds: float = Field(default=8.0, gt=0, le=60)
    client_tool_timeout_seconds: float = Field(default=12.0, gt=0, le=120)
    resend_api_key: SecretStr | None = None
    resend_from: str = "Nirdesh AI <onboarding@resend.dev>"

    knowledge_rag_enabled: bool = False
    openai_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    qdrant_url: str = "http://127.0.0.1:6333"
    knowledge_max_sources_per_user: int = Field(default=50, ge=1, le=1000)
    knowledge_max_source_characters: int = Field(default=500_000, ge=1)
    knowledge_max_upload_bytes: int = Field(default=20_000_000, ge=1)
    knowledge_max_query_characters: int = Field(default=1000, ge=1, le=10_000)
    knowledge_chunk_characters: int = Field(default=1200, ge=100, le=10_000)
    knowledge_chunk_overlap: int = Field(default=150, ge=0, le=2000)
    knowledge_embedding_batch_size: int = Field(default=32, ge=1, le=256)

    jwt_secret: SecretStr = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_seconds: int = Field(default=86_400, gt=0)
    jwt_issuer: str = "nirdeshai"
    jwt_audience: str = "nirdeshai-api"
    otp_ttl_seconds: int = Field(default=600, gt=0)
    otp_max_attempts: int = Field(default=5, ge=1, le=20)

    database_url: str = "sqlite+aiosqlite:///./voiceagent.db"
    database_echo: bool = False
    price_per_minute_paise: int = Field(default=200, gt=0)
    low_balance_warn_paise: int = Field(default=100, ge=0)
    min_voice_balance_paise: int = Field(default=1, ge=1)
    billing_tick_seconds: int = Field(default=1, ge=1, le=30)
    max_recharge_paise: int = Field(default=1_000_000, gt=0)

    vad_end_silence_ms: int = Field(default=650, gt=0)
    vad_barge_in_ms: int = Field(default=300, gt=0)
    vad_pre_roll_ms: int = Field(default=160, ge=0, le=1000)
    vad_speech_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    vad_pre_roll_threshold: float = Field(default=0.2, ge=0.0, le=1.0)
    vad_energy_threshold: float = Field(default=500.0, gt=0)
    vad_provider: Literal["silero", "energy"] = "silero"
    vad_model_path: str | None = None
    endpointing_strategy: Literal["local_vad", "sarvam"] = "local_vad"
    metrics_hud: bool = True
    phrase_chunking_enabled: bool = True
    response_cues_enabled: bool = True
    response_cue_delay_ms: int = Field(default=350, ge=0, le=5_000)
    response_cue_cooldown_turns: int = Field(default=1, ge=0, le=20)
    llm_model: str = "sarvam-105b"
    llm_reasoning_effort: str | None = None
    stt_model: str = "saaras:v3"
    stt_language_code: str = "unknown"
    stt_input_audio_codec: str = "pcm_s16le"
    stt_audio_encoding: str = "audio/wav"
    tts_model: str = "bulbul:v3"
    tts_sample_rate_hz: int = Field(default=24_000, gt=0)
    tts_speaker: str = "shubh"
    tts_language_code: str = "en-IN"
    tts_output_audio_codec: str = "linear16"

    @field_validator(
        "sarvam_api_key",
        "exa_api_key",
        "resend_api_key",
        "openai_api_key",
        "gemini_api_key",
        "llm_reasoning_effort",
        "vad_model_path",
        mode="before",
    )
    @classmethod
    def empty_string_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("jwt_algorithm")
    @classmethod
    def only_hs256_is_supported(cls, value: str) -> str:
        if value != "HS256":
            raise ValueError("only HS256 is supported")
        return value

    @model_validator(mode="before")
    @classmethod
    def load_runtime_secret_files(cls, values: object) -> object:
        if not isinstance(values, dict):
            return values
        resolved = dict(values)
        for field_name, env_name in (
            ("jwt_secret", "JWT_SECRET"),
            ("sarvam_api_key", "SARVAM_API_KEY"),
            ("exa_api_key", "EXA_API_KEY"),
            ("resend_api_key", "RESEND_API_KEY"),
            ("openai_api_key", "OPENAI_API_KEY"),
            ("gemini_api_key", "GEMINI_API_KEY"),
        ):
            if resolved.get(field_name) not in (None, ""):
                continue
            secret_path = os.getenv(f"{env_name}_FILE")
            if not secret_path:
                continue
            resolved[field_name] = Path(secret_path).read_text(encoding="utf-8").strip()
        return resolved

    @cached_property
    def jwt_secret_value(self) -> str:
        return self.jwt_secret.get_secret_value()

    @cached_property
    def openai_api_key_value(self) -> str | None:
        if self.openai_api_key is None:
            return None
        if isinstance(self.openai_api_key, SecretStr):
            return self.openai_api_key.get_secret_value()
        return str(self.openai_api_key)

    @cached_property
    def gemini_api_key_value(self) -> str | None:
        if self.gemini_api_key is None:
            return None
        if isinstance(self.gemini_api_key, SecretStr):
            return self.gemini_api_key.get_secret_value()
        return str(self.gemini_api_key)

    @cached_property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
