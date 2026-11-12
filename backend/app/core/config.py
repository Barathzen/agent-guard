from pathlib import Path

from pydantic_settings import BaseSettings

BACKEND_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = BACKEND_DIR.parent

class Settings(BaseSettings):
    APP_ENV: str = "development"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/agentguard"
    GATEWAY_API_KEY: str = "dev-gateway-key"
    GATEWAY_TIMEOUT_SECONDS: float = 30.0
    RESERVATION_STALENESS_MINUTES: int = 60
    RESERVATION_RECOVERY_INTERVAL_MINUTES: int = 5
    MONITORING_SSE_INTERVAL_SECONDS: float = 5.0
    RUNAWAY_WINDOW_MINUTES: int = 60
    RUNAWAY_MONTHLY_BUDGET_PCT: int = 20

    class Config:
        env_file = (str(BACKEND_DIR / ".env"), str(ROOT_DIR / ".env"))
        extra = "ignore"

settings = Settings()