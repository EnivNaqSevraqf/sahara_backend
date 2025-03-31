from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    # Database settings
    DATABASE_URL: str = "postgresql://avnadmin:AVNS_DkrVvzHCnOiMVJwagav@pg-8b6fabf-sahara-team-8.f.aivencloud.com:17950/defaultdb"
    
    # JWT settings
    SECRET_KEY: str = "a3eca18b09973b1890cfbc94d5322c1aae378b73ea5eee0194ced065175d04aa"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Email settings
    EMAIL_HOST: str = "smtp.gmail.com"
    EMAIL_PORT: int = 587
    EMAIL_HOST_USER: str = "saharaai.noreply@gmail.com"
    EMAIL_HOST_PASSWORD: str = "zfrr wwru xeru rbhf"
    EMAIL_USE_TLS: bool = True
    DEFAULT_FROM_EMAIL: str = "Sahara Team <saharaai.noreply@gmail.com>"

    # File upload settings
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE: int = 5_242_880  # 5MB in bytes
    ALLOWED_EXTENSIONS: set = {'.pdf', '.doc', '.docx', '.txt', '.png', '.jpg', '.jpeg'}

    # API settings
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "Sahara API"
    DEBUG: bool = True
    CORS_ORIGINS: list = ["*"]
    
    # Cache settings
    REDIS_URL: Optional[str] = None
    CACHE_TTL: int = 3600  # 1 hour in seconds

    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    """
    Get settings instance with caching
    Returns:
        Settings instance
    """
    return Settings()