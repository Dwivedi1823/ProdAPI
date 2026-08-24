"""
Centralised configuration for the application.
Uses Pydantic's BaseSettings to load environment variables and provide default values.
This allows for easy management of configuration settings across different environments (development, testing, production).
"""

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

load_dotenv()


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    """

    # OpenAI API key for accessing OpenAI services
    openai_api_key: str = Field(...)
    primary_model: str = Field("gpt-4o-mini")
    fallback_model: str = Field("gpt-4o-mini")

    # Directory path for loading documents
   # DOCUMENTS_DIRECTORY: str = Field(..., env="DOCUMENTS_DIRECTORY")

    #LangSmith
    langsmith_api_key: str = Field(...)
    langchain_tracing_v2: bool = Field(True)
    langsmith_project: str = Field("multi-agent-research-project")

    #Application settings
    app_env: str = Field("development")
    log_level: str = Field("INFO")
    ratelimit_per_minute: int = Field(60)
    cache_ttl_seconds: int = Field(300)
    max_retries: int = Field(3)

    #Model configuration
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


    @property
    def is_production(self) -> bool:
        """
        Check if the application is running in production environment.
        """
        return self.app_env.lower() == "production"
    
@lru_cache
def get_settings() -> Settings:
    """
    Get the application settings, cached for performance, loaded once and reused across the application.
    This function uses LRU caching to ensure that the settings are only loaded once, improving performance
    """
    return Settings()