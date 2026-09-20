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
    SECRET_KEY: str = os.getenv("SECRET_KEY", "chikitsasetu-super-secret-key-change-in-production-2026")
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
        """Validates that insecure default secrets are not deployed in production."""
        if self.ENV == "production" and "change-in-production" in self.SECRET_KEY:
            import warnings
            warnings.warn(
                "CRITICAL SECURITY WARNING: Default insecure SECRET_KEY detected in production environment! "
                "Configure a high-entropy SECRET_KEY via environment variables.",
                RuntimeWarning,
                stacklevel=2
            )
    
    # ML Artifacts
    ML_ARTIFACTS_DIR: Path = BASE_DIR / "ml" / "artifacts"
    
    # Network Ports
    FLASK_PORT: int = int(os.getenv("FLASK_PORT", "5000"))
    FASTAPI_PORT: int = int(os.getenv("FASTAPI_PORT", "8000"))

settings = Settings()
settings.validate_production_secrets()
