import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field, validator

from src.utils import SecretManager
secret_manager = SecretManager()

class Settings(BaseSettings):
    gemini_api_key: str = Field(default="", env="GEMINI_API_KEY")
    mimo_api_key: str = Field(default="", env="MIMO_API_KEY")
    mimo_base_url: str = Field(default="https://api.xiaomimimo.com/v1", env="MIMO_BASE_URL")
    mimo_rpm_limit: int = Field(default=100, env="MIMO_RPM_LIMIT")
    mimo_daily_limit: int = Field(default=5000, env="MIMO_DAILY_LIMIT")
    
    openrouter_api_key: str = Field(default="", env="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", env="OPENROUTER_BASE_URL")
    
    sentry_dsn: str = Field(default="", env="SENTRY_DSN")
    github_token: str = Field(default="", env="GITHUB_TOKEN")
    model_sign_key: str = Field(default="", env="MODEL_SIGN_KEY")
    
    @validator("model_sign_key", pre=True, always=True)
    def validate_model_sign_key(cls, v):
        env = os.getenv("ENV", "production").lower()
        if env in ("testing", "test", "ci"):
            # У CI/тестах дозволяємо dummy-ключ — безпека не потрібна
            return v or "ci-insecure-test-key-000000"
        # Production: жорстка перевірка
        if not v or v == "dev-local-key" or len(v) < 32:
            raise ValueError(
                "Insecure MODEL_SIGN_KEY configuration. "
                "Must provide a secure random string (min 32 chars)."
            )
        return v
    
    db_path: Path = Field(default=Path("data/dp_shw.duckdb"))
    log_path: Path = Field(default=Path("logs/app.log"))
    cache_dir: Path = Field(default=Path("data/cache"))
    models_dir: Path = Field(default=Path("data/models"))
    
    scrape_delay_seconds: float = 2.0
    max_projects_per_hackathon: int = 500
    max_html_size: int = 5 * 1024 * 1024
    
    cpu_cores: int = Field(default=2, env="CPU_CORES")  # Обмеження для слабкого CPU (напр. AMD A4)

    @validator('db_path', 'log_path', 'cache_dir', 'models_dir')
    def ensure_absolute(cls, v):
        return v if v.is_absolute() else Path(__file__).resolve().parent.parent / v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

SETTINGS = Settings()

# Post-processing for encrypted keys
enc_mimo = os.getenv("MIMO_API_KEY_ENCRYPTED")
if enc_mimo:
    SETTINGS.mimo_api_key = secret_manager.decrypt(enc_mimo.encode())
elif not SETTINGS.mimo_api_key:
    SETTINGS.mimo_api_key = SETTINGS.gemini_api_key

enc_openrouter = os.getenv("OPENROUTER_API_KEY_ENCRYPTED")
if enc_openrouter:
    SETTINGS.openrouter_api_key = secret_manager.decrypt(enc_openrouter.encode())

# Backward compatibility bindings
DB_PATH = SETTINGS.db_path
CACHE_DIR = SETTINGS.cache_dir
SENTRY_DSN = SETTINGS.sentry_dsn
MIMO_API_KEY = SETTINGS.mimo_api_key
MIMO_BASE_URL = SETTINGS.mimo_base_url
MIMO_RPM_LIMIT = SETTINGS.mimo_rpm_limit
MIMO_DAILY_LIMIT = SETTINGS.mimo_daily_limit
OPENROUTER_API_KEY = SETTINGS.openrouter_api_key
OPENROUTER_BASE_URL = SETTINGS.openrouter_base_url
SCRAPE_DELAY_SECONDS = SETTINGS.scrape_delay_seconds
MAX_PROJECTS_PER_HACKATHON = SETTINGS.max_projects_per_hackathon
