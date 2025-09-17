import os
from pydantic_settings import BaseSettings
from typing import List
import secrets
from dotenv import load_dotenv

load_dotenv(override=True)

class Settings(BaseSettings):
    # Project
    PROJECT_NAME: str = "AI Assessment Platform"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    
    # Security
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200  # 30 days
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL","")
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001", 
        "http://localhost:8080"
    ]
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()