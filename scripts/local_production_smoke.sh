#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="${PYTHON_BIN_FALLBACK:-python3}"
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
READYZ_URL="http://$HOST:$PORT/readyz?write=1"
HEALTHZ_URL="http://$HOST:$PORT/healthz"
LOG_FILE="${LOG_FILE:-$ROOT_DIR/tmp/local-production-smoke.log}"
PID_FILE="${PID_FILE:-$ROOT_DIR/tmp/local-production-smoke.pid}"

mkdir -p "$ROOT_DIR/tmp"

if [ -z "${DATABASE_URL:-}" ]; then
  echo "[smoke] DATABASE_URL is required, for example:" >&2
  echo "[smoke] DATABASE_URL='postgresql://werewolf:werewolf@127.0.0.1:5432/werewolf_stats' sh scripts/local_production_smoke.sh" >&2
  exit 2
fi

export APP_DIR="${APP_DIR:-$ROOT_DIR}"
export PYTHON_BIN
export HOST
export PORT
export ENABLE_POSTGRES_WRITES="${ENABLE_POSTGRES_WRITES:-1}"
export WEB_LOGIN_BASE_URL="${WEB_LOGIN_BASE_URL:-https://wolf.metauniverse-cn.xyz}"
export COOKIE_SECURE="${COOKIE_SECURE:-1}"
export WECHAT_MINIPROGRAM_APPID="${WECHAT_MINIPROGRAM_APPID:-local-smoke-appid}"
export WECHAT_MINIPROGRAM_SECRET="${WECHAT_MINIPROGRAM_SECRET:-local-smoke-secret}"
export INSTALL_REQUIREMENTS="${INSTALL_REQUIREMENTS:-0}"
export RUN_PRODUCTION_CONFIG_CHECK="${RUN_PRODUCTION_CONFIG_CHECK:-1}"
export APPLY_SCHEMA="${APPLY_SCHEMA:-1}"
export RUN_SCHEMA_CHECK="${RUN_SCHEMA_CHECK:-1}"
export RUN_SMOKE="${RUN_SMOKE:-1}"
export RUN_LOG_CLEANUP="${RUN_LOG_CLEANUP:-0}"
export REQUIRE_DATABASE_URL="${REQUIRE_DATABASE_URL:-1}"

cleanup() {
  if [ -f "$PID_FILE" ]; then
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
  fi
}
trap cleanup EXIT INT TERM

echo "[smoke] running pre-deploy check"
"$PYTHON_BIN" "$ROOT_DIR/scripts/pre_deploy_check.py" --skip-backup

echo "[smoke] starting production server on $HOST:$PORT"
sh "$ROOT_DIR/scripts/start_production.sh" >"$LOG_FILE" 2>&1 &
server_pid="$!"
echo "$server_pid" >"$PID_FILE"

echo "[smoke] waiting for health checks"
i=0
while [ "$i" -lt 30 ]; do
  if "$PYTHON_BIN" - "$HEALTHZ_URL" "$READYZ_URL" <<'PY'
import json
import sys
import urllib.request

healthz_url, readyz_url = sys.argv[1], sys.argv[2]
with urllib.request.urlopen(healthz_url, timeout=2) as response:
    if response.status != 200:
        raise SystemExit(1)
with urllib.request.urlopen(readyz_url, timeout=3) as response:
    payload = json.loads(response.read().decode("utf-8"))
    if response.status != 200 or not payload.get("ok"):
        raise SystemExit(1)
    print("[smoke] readyz ok:", payload.get("database", {}).get("backend", "unknown"))
PY
  then
    echo "[smoke] production smoke passed"
    echo "[smoke] log: $LOG_FILE"
    exit 0
  fi
  if ! kill -0 "$server_pid" 2>/dev/null; then
    echo "[smoke] server exited early; last log lines:" >&2
    tail -n 80 "$LOG_FILE" >&2 || true
    exit 1
  fi
  i=$((i + 1))
  sleep 1
done

echo "[smoke] health checks did not pass in time; last log lines:" >&2
tail -n 120 "$LOG_FILE" >&2 || true
exit 1
