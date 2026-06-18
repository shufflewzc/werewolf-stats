#!/usr/bin/env sh
set -eu

APP_DIR="${APP_DIR:-/app}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-2}"
GUNICORN_THREADS="${GUNICORN_THREADS:-4}"
GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-120}"
INSTALL_REQUIREMENTS="${INSTALL_REQUIREMENTS:-1}"
APPLY_SCHEMA="${APPLY_SCHEMA:-1}"
RUN_SCHEMA_CHECK="${RUN_SCHEMA_CHECK:-1}"
RUN_INDEX_CHECK="${RUN_INDEX_CHECK:-1}"
RUN_SMOKE="${RUN_SMOKE:-1}"
RUN_LOG_CLEANUP="${RUN_LOG_CLEANUP:-1}"
RUN_PRODUCTION_CONFIG_CHECK="${RUN_PRODUCTION_CONFIG_CHECK:-1}"
REQUIRE_DATABASE_URL="${REQUIRE_DATABASE_URL:-1}"

cd "$APP_DIR"
export PYTHONPATH="${PYTHONPATH:-scripts}"
export ENABLE_POSTGRES_WRITES="${ENABLE_POSTGRES_WRITES:-1}"

echo "[start] app_dir=$APP_DIR"
echo "[start] host=$HOST port=$PORT workers=$GUNICORN_WORKERS threads=$GUNICORN_THREADS timeout=$GUNICORN_TIMEOUT"

if [ "$REQUIRE_DATABASE_URL" = "1" ] && [ -z "${DATABASE_URL:-}" ]; then
  echo "[start] DATABASE_URL is required for production startup" >&2
  exit 1
fi

if [ "$INSTALL_REQUIREMENTS" = "1" ]; then
  echo "[start] installing requirements"
  "$PYTHON_BIN" -m pip install --break-system-packages -r requirements.txt
fi

if [ "$RUN_PRODUCTION_CONFIG_CHECK" = "1" ]; then
  echo "[start] checking production configuration"
  "$PYTHON_BIN" scripts/production_config_check.py
fi

if [ "$APPLY_SCHEMA" = "1" ]; then
  echo "[start] applying database schema"
  "$PYTHON_BIN" scripts/apply_postgres_schema.py
fi

if [ "$RUN_SCHEMA_CHECK" = "1" ]; then
  echo "[start] checking runtime schema"
  "$PYTHON_BIN" scripts/check_runtime_schema.py
fi

if [ "$RUN_INDEX_CHECK" = "1" ]; then
  echo "[start] checking postgres indexes"
  "$PYTHON_BIN" scripts/check_postgres_indexes.py --strict
fi

if [ "$RUN_SMOKE" = "1" ]; then
  echo "[start] running runtime smoke"
  "$PYTHON_BIN" scripts/runtime_db_smoke.py
fi

if [ "$RUN_LOG_CLEANUP" = "1" ]; then
  echo "[start] cleaning expired logs"
  "$PYTHON_BIN" scripts/cleanup_logs.py
fi

echo "[start] launching gunicorn"
exec "$PYTHON_BIN" -m gunicorn \
  -w "$GUNICORN_WORKERS" \
  -k gthread \
  --threads "$GUNICORN_THREADS" \
  -t "$GUNICORN_TIMEOUT" \
  -b "$HOST:$PORT" \
  --chdir "$APP_DIR" \
  wsgi:app
