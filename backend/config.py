import os
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
    PROJECT_NAME: str = "CHIKITSASETU"
    PROJECT_TAGLINE: str = "Smart Hospital Management & Healthcare Analytics System"
    PROJECT_VERSION: str = "1.0.0"
    
    # Environment & Database
    ENV: str = os.getenv("ENV", "development")
    USE_SQLITE: bool = os.getenv("USE_SQLITE", "false").lower() in ("true", "1", "yes")
    
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER", "localhost")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "chikitsasetu")
    
    @property
    def POSTGRES_DATABASE_URL(self) -> str:
        return f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def SQLITE_PATH(self) -> Path:
        return BASE_DIR / "chikitsasetu_dev.db"

    @property
    def DATABASE_URL(self) -> str:
        custom_url = os.getenv("DATABASE_URL")
        if self.ENV == "production":
            if self.USE_SQLITE:
                raise RuntimeError(
                    "CRITICAL CONFIGURATION ERROR: USE_SQLITE is strictly forbidden in production! "
                    "PostgreSQL must be explicitly configured."
                )
            if custom_url:
                if custom_url.startswith("sqlite"):
                    raise RuntimeError(
                        "CRITICAL CONFIGURATION ERROR: SQLite database URL is strictly forbidden in production! "
                        "PostgreSQL must be configured."
                    )
                return custom_url
            # In production, use explicit PostgreSQL connection URL; NEVER silently fall back to SQLite
            return self.POSTGRES_DATABASE_URL

        if custom_url:
            return custom_url
        if self.USE_SQLITE or os.getenv("TESTING") == "1":
            return f"sqlite:///{self.SQLITE_PATH}"
        
        # Check if psycopg2 is available and PostgreSQL port is listening
        try:
            import psycopg2  # noqa: F401
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            is_open = sock.connect_ex((self.POSTGRES_SERVER, int(self.POSTGRES_PORT))) == 0
            sock.close()
            if is_open:
                return self.POSTGRES_DATABASE_URL
            return f"sqlite:///{self.SQLITE_PATH}"
        except Exception:
            return f"sqlite:///{self.SQLITE_PATH}"

    # Security
    @property
    def SECRET_KEY(self) -> str:
        key = os.getenv("SECRET_KEY")
        if self.ENV == "production":
            if not key or "change-in-production" in key or "development-secret-key" in key:
                raise RuntimeError(
                    "CRITICAL CONFIGURATION ERROR: SECRET_KEY must be explicitly set via environment variable in production! "
                    "Default or insecure secret keys are strictly forbidden."
                )
            return key
        return key or "chikitsasetu-development-secret-key-not-for-production"

    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours for dev convenience
    
    # Secure Cookies & Origins
    SESSION_COOKIE_SECURE: bool = os.getenv(
        "SESSION_COOKIE_SECURE",
        "true" if os.getenv("ENV") == "production" else "false"
    ).lower() in ("true", "1", "yes")

    @property
    def ALLOWED_ORIGINS(self) -> list[str]:
        origins_env = os.getenv("ALLOWED_ORIGINS")
        if origins_env:
            return [o.strip() for o in origins_env.split(",") if o.strip()]
        return [
            "http://localhost:3000",
            "http://localhost:5000",
            "http://127.0.0.1:5000",
            "http://localhost:8000",
            "http://127.0.0.1:8000"
        ]

    def validate_production_secrets(self):
        """Validates that production environment has secure secrets and PostgreSQL configured."""
        if self.ENV == "production":
            # Will raise RuntimeError if SECRET_KEY or DATABASE_URL is missing or invalid
            _ = self.SECRET_KEY
            _ = self.DATABASE_URL
    
    # ML Artifacts
    ML_ARTIFACTS_DIR: Path = BASE_DIR / "ml" / "artifacts"
    
    # AI Health Assistant Configuration
    CHATBOT_PROVIDER: str = os.getenv("CHATBOT_PROVIDER", "auto")  # "auto", "gemini", "openai", or "local"
    CHATBOT_API_KEY: Optional[str] = (
        os.getenv("CHATBOT_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")
    )
    CHATBOT_MODEL: str = os.getenv("CHATBOT_MODEL", "gemini-1.5-flash")
    CHATBOT_API_BASE: Optional[str] = os.getenv("CHATBOT_API_BASE")
    CHATBOT_MAX_UPLOAD_BYTES: int = int(os.getenv("CHATBOT_MAX_UPLOAD_BYTES", 10 * 1024 * 1024))  # 10MB
    CHATBOT_UPLOAD_DIR: Path = BASE_DIR / "uploads" / "chatbot_temp"

    # Network Ports
    FLASK_PORT: int = int(os.getenv("FLASK_PORT", "5000"))
    FASTAPI_PORT: int = int(os.getenv("FASTAPI_PORT", "8000"))

settings = Settings()
settings.validate_production_secrets()
# Ensure upload directory exists
settings.CHATBOT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
