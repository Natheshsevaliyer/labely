# app/core/config.py - Add Redis settings
import os
from typing import Optional, Set
from urllib.parse import quote_plus

from pydantic import ConfigDict, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    # Server
    PORT: int = Field(8000, validation_alias="PORT")
    HOST: str = Field("0.0.0.0", validation_alias="HOST")
    WORKERS: int = Field(1, validation_alias="WORKERS")

    # Environment
    ENVIRONMENT: str
    DEBUG: bool = False

    # App
    APP_NAME: str = "EMD Label Generator"
    SECRET_KEY: str
    BASE_URL: str
    FRONTEND_URL: str

    # --- ADD THESE LINES STARTING HERE ---
    # Cookie Settingsclass Settings:
    COOKIE_NAME: str = "labely_session"
    REFRESH_COOKIE_NAME: str = "refresh_token"
    COOKIE_SECURE: bool = False  # Set to True in production (HTTPS)
    COOKIE_HTTPONLY: bool = True
    COOKIE_SAMESITE: str = "none"  # Required for cross-site XHR auth

    # Expiry in seconds
    ACCESS_TOKEN_EXPIRE_SECONDS: int = 28800  # 8 hours
    REFRESH_TOKEN_EXPIRE_SECONDS: int = 2592000  # 30 days
    # --------------------------------------
    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_MAX_CONNECTIONS: int = 10

    # Redis TTLs (in seconds)
    REDIS_SESSION_TTL: int = 28800 #28800  # 8 hours
    REDIS_PROCESS_TTL: int = 86400  # 24 hours
    REDIS_CACHE_TTL: int = 300  # 5 minutes
    REDIS_RATE_LIMIT_WINDOW: int = 60  # 1 minute
    REDIS_LOCK_TIMEOUT: int = 30  # 30 seconds

    # Database
    DB_MODE: str = "tcp"  # "tcp" or "socket"
    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str

    # Email
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = Field("mabroukcontact360@gmail.com", validation_alias="SMTP_USERNAME")
    SMTP_PASSWORD: str = Field("mzgpacky drax gjlq", validation_alias="SMTP_PASSWORD")
    FROM_EMAIL: str = Field("noreply@example.com", validation_alias="FROM_EMAIL")

    # Mirakl
    MIRAKL_BASE_URL: str
    MIRAKL_API_KEY: str
    MIRAKL_SHOP_ID: int
    MIRAKL_QUANTITY_FETCH_DAYS: int = 60  # How many days back to fetch orders for quantity-based generation (default: 60 days)

    # SRP
    SRP_ENDPOINT_URI: str
    SRP_USERNAME: str
    SRP_CLIENT_ID: str
    SRP_PASSWORD: str
    SRP_GETTOKEN_URI: str = "/api/label/v1/auth/token"
    SRP_CREATELABEL_URI: str = "/api/label/v1/create"
    SRP_ISALIVE_URI: str = "/api/label/v1/isalive"
    SRP_MAX_CONCURRENT: int = 100
    SRP_REQUEST_TIMEOUT: int = 60
    SRP_MAX_RETRIES: int = 2

    #batch processing
    BATCH_SIZE: int = 2  # Adjust: 1 = per-order, 5-10 = small batches, 20+ = fewer updates

    # File Storage
    OUTPUT_FOLDER: str = "./output"
    FILE_CLEANUP_MINUTES: int = 30
    ALLOWED_EXTENSIONS: Set[str] = {"pdf"}

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Security
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_HOURS: int = 8

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
    )

    @property
    def REDIS_URL(self) -> str:
        """Get Redis URL."""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def DATABASE_URL(self) -> str:
        """Get database URL based on environment."""
        encoded_password = quote_plus(self.DB_PASSWORD)

        if self.DB_MODE == "socket":
            # Cloud SQL Unix socket
            return (
                f"mysql+mysqlconnector://{self.DB_USER}:{encoded_password}"
                f"@/{self.DB_NAME}?unix_socket={self.DB_HOST}"
            )
        else:
            # Default: TCP (Docker / EC2 / Local)
            return (
                f"mysql+mysqlconnector://{self.DB_USER}:{encoded_password}"
                f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            )

    def ensure_directories(self):
        """Create necessary directories."""
        os.makedirs(self.OUTPUT_FOLDER, exist_ok=True)

# Create global settings instance
settings = Settings()
settings.ensure_directories()

if settings.DEBUG:
    print(f"Running in {settings.ENVIRONMENT} mode")
    print(f"Redis URL: {settings.REDIS_URL}")
    print(f"Database URL: {settings.DATABASE_URL[:50]}...")
