from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./dados.db"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Origens permitidas no CORS (separadas por vírgula).
    # Em produção, defina ALLOWED_ORIGINS com o domínio real, ex.:
    #   ALLOWED_ORIGINS=https://visia.onrender.com
    # Em desenvolvimento, mantém o localhost padrão.
    ALLOWED_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def origens_permitidas(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


settings = Settings()
