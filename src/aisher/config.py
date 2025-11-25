import logging
from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application configuration with security best practices"""
    CLICKHOUSE_HOST: str = "localhost"
    CLICKHOUSE_PORT: int = 8123
    CLICKHOUSE_USER: str = "default"
    CLICKHOUSE_PASSWORD: SecretStr = SecretStr("")
    CLICKHOUSE_DATABASE: str = "signoz_traces"

    LLM_MODEL: str = "gpt-4-turbo"
    OPENAI_API_KEY: SecretStr = SecretStr("sk-...")

    # Performance tuning
    QUERY_TIMEOUT: int = 30
    LLM_TIMEOUT: int = 45
    MAX_RETRIES: int = 3

    # Smart truncation
    STACK_MAX_LENGTH: int = 600
    STACK_HEAD_LENGTH: int = 250
    STACK_TAIL_LENGTH: int = 350

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding='utf-8',
        extra='ignore'
    )

    @field_validator('OPENAI_API_KEY')
    @classmethod
    def validate_api_key(cls, v: SecretStr) -> SecretStr:
        if v.get_secret_value().startswith('sk-...'):
            logger.warning("⚠️  Using placeholder API key. Set OPENAI_API_KEY in .env")
        return v


settings = Settings()
