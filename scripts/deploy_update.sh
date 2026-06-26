#!/usr/bin/env sh
set -eu

APP_DIR="${APP_DIR:-/opt/werewolf-stats}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env.production}"
ENV_FILE_SET=0
SERVICE_NAME="${SERVICE_NAME:-werewolf-stats}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RUN_GIT_PULL="${RUN_GIT_PULL:-1}"
RUN_REQUIREMENTS="${RUN_REQUIREMENTS:-1}"
RUN_APPLY_SCHEMA="${RUN_APPLY_SCHEMA:-1}"
RUN_PRE_DEPLOY_CHECK="${RUN_PRE_DEPLOY_CHECK:-1}"
RUN_NGINX_CHECK="${RUN_NGINX_CHECK:-1}"
RESTART_SERVICE="${RESTART_SERVICE:-1}"
SHOW_STATUS="${SHOW_STATUS:-1}"

usage() {
  cat <<'EOF'
Usage: sh scripts/deploy_update.sh [options]

Options:
  --app-dir PATH          Project directory. Default: /opt/werewolf-stats
  --env-file PATH         Production env file. Default: APP_DIR/.env.production
  --service NAME          systemd service name. Default: werewolf-stats
  --no-pull               Skip git pull
  --no-requirements       Skip pip install -r requirements.txt
  --no-schema             Skip scripts/apply_postgres_schema.py
  --no-check              Skip scripts/pre_deploy_check.py
  --no-nginx-check        Skip nginx -t and reload
  --no-restart            Skip service restart
  --no-status             Skip final service status output
  -h, --help              Show this help

Environment overrides are also supported:
  APP_DIR, ENV_FILE, SERVICE_NAME, PYTHON_BIN,
  RUN_GIT_PULL, RUN_REQUIREMENTS, RUN_APPLY_SCHEMA, RUN_PRE_DEPLOY_CHECK,
  RUN_NGINX_CHECK, RESTART_SERVICE, SHOW_STATUS
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --app-dir)
      APP_DIR="$2"
      if [ "$ENV_FILE_SET" = "0" ]; then
        ENV_FILE="$APP_DIR/.env.production"
      fi
      shift 2
      ;;
    --env-file)
      ENV_FILE="$2"
      ENV_FILE_SET=1
      shift 2
      ;;
    --service)
      SERVICE_NAME="$2"
      shift 2
      ;;
    --no-pull)
      RUN_GIT_PULL=0
      shift
      ;;
    --no-requirements)
      RUN_REQUIREMENTS=0
      shift
      ;;
    --no-schema)
      RUN_APPLY_SCHEMA=0
      shift
      ;;
    --no-check)
      RUN_PRE_DEPLOY_CHECK=0
      shift
      ;;
    --no-nginx-check)
      RUN_NGINX_CHECK=0
      shift
      ;;
    --no-restart)
      RESTART_SERVICE=0
      shift
      ;;
    --no-status)
      SHOW_STATUS=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[deploy] unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

run() {
  echo
  echo "[deploy] $*"
  "$@"
}

if [ ! -d "$APP_DIR" ]; then
  echo "[deploy] app directory not found: $APP_DIR" >&2
  exit 1
fi

cd "$APP_DIR"

if [ ! -f "$ENV_FILE" ]; then
  echo "[deploy] env file not found: $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

export APP_DIR
export PYTHONPATH="${PYTHONPATH:-scripts}"
export ENABLE_POSTGRES_WRITES="${ENABLE_POSTGRES_WRITES:-1}"

echo "[deploy] app_dir=$APP_DIR"
echo "[deploy] env_file=$ENV_FILE"
echo "[deploy] service=$SERVICE_NAME"

if [ "$RUN_GIT_PULL" = "1" ]; then
  run git pull --ff-only
fi

if [ "$RUN_REQUIREMENTS" = "1" ]; then
  run "$PYTHON_BIN" -m pip install --break-system-packages -r requirements.txt
fi

if [ "$RUN_APPLY_SCHEMA" = "1" ]; then
  run "$PYTHON_BIN" scripts/apply_postgres_schema.py
fi

if [ "$RUN_PRE_DEPLOY_CHECK" = "1" ]; then
  run "$PYTHON_BIN" scripts/pre_deploy_check.py
fi

if [ "$RUN_NGINX_CHECK" = "1" ]; then
  run sudo nginx -t
  run sudo systemctl reload nginx
fi

if [ "$RESTART_SERVICE" = "1" ]; then
  run sudo systemctl restart "$SERVICE_NAME"
fi

if [ "$SHOW_STATUS" = "1" ]; then
  echo
  echo "[deploy] service status:"
  sudo systemctl --no-pager --lines=20 status "$SERVICE_NAME"
fi

echo
echo "[deploy] done"
