"""
Configuration management for ClimateRisk Intel backend.
Loads all settings from environment variables.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # API Tokens
    noaa_token: str = ""
    anthropic_api_key: str = ""
    huggingface_token: str = ""

    # Server
    backend_port: int = 8000
    cors_origins: str = "http://localhost:3000"

    # App
    log_level: str = "INFO"
    app_name: str = "ClimateRisk Intel API"
    app_version: str = "0.1.0"

    # Feature flags
    enable_prithvi: bool = False  # Set True when HuggingFace token is available
    enable_climada: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
