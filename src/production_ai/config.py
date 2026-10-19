from pathlib import Path
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

class Principal(BaseModel):
    user_id: str = Field(min_length=1, max_length=80)
    role: str = Field(pattern=r"^(user|admin)$")

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    api_keys: dict[str, Principal] = Field(default_factory=dict)
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    model_timeout_seconds: float = Field(default=120, gt=0, le=600)
    max_input_chars: int = Field(default=8000, ge=1, le=32000)
    max_output_chars: int = Field(default=12000, ge=1, le=64000)
    max_body_bytes: int = Field(default=16384, ge=1024, le=65536)
    memory_turns: int = Field(default=8, ge=1, le=32)
    memory_ttl_seconds: int = Field(default=86400, ge=60)
    max_sessions: int = Field(default=1000, ge=1)
    requests_per_minute: int = Field(default=20, ge=1)
    max_concurrent_generations: int = Field(default=2, ge=1, le=32)
    max_output_tokens: int = Field(default=1024, ge=32, le=4096)
    log_max_bytes: int = Field(default=5242880, ge=1024)
    log_backup_count: int = Field(default=3, ge=1, le=20)

    @model_validator(mode="after")
    def secure_keys(self):
        if not self.api_keys or any(len(k) < 32 or k.startswith("REPLACE_") for k in self.api_keys):
            raise ValueError("Configure generated API keys of at least 32 characters in .env")
        if not any(p.role == "admin" for p in self.api_keys.values()):
            raise ValueError("At least one admin key is required")
        if not self.ollama_url.startswith(("http://", "https://")):
            raise ValueError("OLLAMA_URL must be an HTTP(S) URL")
        return self
