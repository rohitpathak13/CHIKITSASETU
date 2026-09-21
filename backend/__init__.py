"""
CHIKITSASETU - Backend Application Package
Exposes core backend utilities, database bindings, models, services, and application factories.
"""
import sys
from pathlib import Path

# Ensure backend package and submodules are accessible
from backend.config import settings
from backend.database import db_session, init_db, Base, SessionLocal, get_db
from backend.app import create_app

__all__ = [
    "create_app",
    "settings",
    "db_session",
    "init_db",
    "Base",
    "SessionLocal",
    "get_db",
]

# Compatibility layer: Register legacy module aliases in sys.modules
# to support any legacy imports without runtime failure.
try:
    import backend.models as _models
    import backend.services as _services
    import backend.config as _config
    import backend.database as _database
    import backend.security as _security
    import backend.utils.decorators as _decorators
    import backend.fastapi_service as _fastapi_service

    sys.modules.setdefault("core", sys.modules[__name__])
    sys.modules.setdefault("core.config", _config)
    sys.modules.setdefault("core.database", _database)
    sys.modules.setdefault("core.security", _security)
    sys.modules.setdefault("core.models", _models)
    sys.modules.setdefault("core.services", _services)
    sys.modules.setdefault("web", sys.modules["backend.app"])
    sys.modules.setdefault("web.decorators", _decorators)
    sys.modules.setdefault("api", _fastapi_service)
except Exception:
    pass
