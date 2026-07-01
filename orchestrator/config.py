"""
Ayarlar — tek yerden yönetilir, .env'den okunur (pydantic-settings).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Groq (function-calling destekli, ücretsiz) — https://console.groq.com
    groq_api_key: str | None = None
    model: str = "llama-3.3-70b-versatile"

    # --- Planlayıcı ---
    max_replans: int = 2             # planlayıcı en fazla kaç kez planı revize edebilir
    max_plan_steps: int = 5          # tek bir planda en fazla kaç adım olabilir

    # --- Yürütücü (her adım için bağımsız bir mini ReAct döngüsü) ---
    max_tool_calls_per_step: int = 3

    # --- Araç ayarları ---
    search_results: int = 5
    max_read_chars: int = 3000


settings = Settings()
