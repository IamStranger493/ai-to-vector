import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    API_KEY: str = Field(default="", description="Secret API key required for auth")
    ALLOWED_ORIGINS: str = Field(
        default="http://localhost:5173",
        description="Comma-separated list of allowed CORS origins"
    )
    MAX_UPLOAD_MB: int = Field(default=12, description="Max upload size in megabytes")
    MAX_IMAGE_PIXELS: int = Field(default=50_000_000, description="Pillow max image pixels")
    MAX_CONCURRENT_JOBS: int = Field(default=1, description="Max concurrent processing jobs")
    QUEUE_LENGTH_CAP: int = Field(default=3, description="Max queued jobs before 429")
    JOB_TIMEOUT_S: int = Field(default=300, description="Max job runtime in seconds")
    JOB_TTL_S: int = Field(default=900, description="Time to keep job results in seconds (15 min)")
    PORT: int = Field(default=10000, description="Server port")

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]


settings = Settings()
