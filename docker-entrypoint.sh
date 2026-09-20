#!/bin/sh
set -e

echo "[docker-entrypoint] Starting MediCare AI container service: $1"

# Database connection parameters from environment
DB_HOST="${POSTGRES_SERVER:-db}"
DB_PORT="${POSTGRES_PORT:-5432}"

echo "[docker-entrypoint] Waiting for database at ${DB_HOST}:${DB_PORT}..."
python - <<EOF
import socket
import time
import sys

host = "${DB_HOST}"
port = int("${DB_PORT}")
timeout = 60
start_time = time.time()

while True:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        result = sock.connect_ex((host, port))
        sock.close()
        if result == 0:
            print(f"[docker-entrypoint] Database connection established at {host}:{port}.")
            sys.exit(0)
    except Exception as e:
        pass
    
    if time.time() - start_time > timeout:
        print(f"[docker-entrypoint] Timeout waiting for database {host}:{port}.")
        sys.exit(1)
        
    time.sleep(1)
EOF

echo "[docker-entrypoint] Ensuring database schema and tables exist..."
python -c "from core.database import init_db; init_db()"

echo "[docker-entrypoint] Checking for existing master seed records..."
python - <<EOF
import sys
try:
    from core.database import SessionLocal
    from core.models import User
    db = SessionLocal()
    user_count = db.query(User).count()
    db.close()
    if user_count == 0:
        print("[docker-entrypoint] Database is empty. Seeding initial hospital data...")
        from scripts.seed_database import seed
        seed()
        print("[docker-entrypoint] Seeding completed successfully.")
    else:
        print(f"[docker-entrypoint] Database already initialized ({user_count} users found). Skipping seed.")
except Exception as e:
    print(f"[docker-entrypoint] Warning during bootstrap check: {e}")
EOF

if [ "$1" = "api" ]; then
    echo "[docker-entrypoint] Launching FastAPI ASGI engine via Uvicorn..."
    exec uvicorn api.main:app --host 0.0.0.0 --port "${FASTAPI_PORT:-8000}" --workers "${UVICORN_WORKERS:-2}"
elif [ "$1" = "web" ]; then
    echo "[docker-entrypoint] Launching Flask WSGI portal via Gunicorn..."
    exec gunicorn -w "${GUNICORN_WORKERS:-4}" -b "0.0.0.0:${FLASK_PORT:-5000}" "web:create_app()"
else
    echo "[docker-entrypoint] Executing custom command: $@"
    exec "$@"
fi
