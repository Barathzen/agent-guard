from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_ENV: str = "development"
    DATABASE_URL: str = "postgresql+asyncpg://agentguard:local_dev_password@localhost:5432/agentguard"
    GATEWAY_API_KEY: str = "dev-gateway-key"
    GATEWAY_TIMEOUT_SECONDS: float = 30.0

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()