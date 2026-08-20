#!/usr/bin/env sh
set -eu

APP_DIR="${APP_DIR:-/opt/werewolf-stats}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env.production}"
ENV_FILE_SET=0
SERVICE_NAME="${SERVICE_NAME:-werewolf-stats}"
IMPORT_WORKER_SERVICE="${IMPORT_WORKER_SERVICE:-werewolf-stats-import-worker}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RUN_GIT_PULL="${RUN_GIT_PULL:-1}"
RUN_REQUIREMENTS="${RUN_REQUIREMENTS:-1}"
RUN_APPLY_SCHEMA="${RUN_APPLY_SCHEMA:-1}"
RUN_PRE_DEPLOY_CHECK="${RUN_PRE_DEPLOY_CHECK:-1}"
RUN_NGINX_CHECK="${RUN_NGINX_CHECK:-1}"
RESTART_SERVICE="${RESTART_SERVICE:-1}"
RUN_WARM_PUBLIC_CACHE="${RUN_WARM_PUBLIC_CACHE:-1}"
WARM_CACHE_ROUNDS="${WARM_CACHE_ROUNDS:-2}"
SERVICE_READY_ATTEMPTS="${SERVICE_READY_ATTEMPTS:-30}"
SERVICE_READY_DELAY="${SERVICE_READY_DELAY:-1}"
SHOW_STATUS="${SHOW_STATUS:-1}"
PREVIOUS_COMMIT=""
DEPLOY_UPDATED=0

rollback_on_error() {
  exit_code=$?
  trap - EXIT INT TERM HUP
  if [ "$DEPLOY_UPDATED" = "1" ] && [ -n "$PREVIOUS_COMMIT" ]; then
    echo "[deploy] deployment failed; rolling back to $PREVIOUS_COMMIT" >&2
    sudo systemctl stop "$IMPORT_WORKER_SERVICE" >/dev/null 2>&1 || true
    git reset --hard "$PREVIOUS_COMMIT" || true
    sudo systemctl restart "$SERVICE_NAME" || true
    sudo systemctl restart "$IMPORT_WORKER_SERVICE" || true
  fi
  exit "$exit_code"
}

trap rollback_on_error EXIT INT TERM HUP

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
  --no-warm-cache         Skip post-restart public API cache warming
  --no-status             Skip final service status output
  -h, --help              Show this help

Environment overrides are also supported:
  APP_DIR, ENV_FILE, SERVICE_NAME, PYTHON_BIN,
  RUN_GIT_PULL, RUN_REQUIREMENTS, RUN_APPLY_SCHEMA, RUN_PRE_DEPLOY_CHECK,
  RUN_NGINX_CHECK, RESTART_SERVICE, RUN_WARM_PUBLIC_CACHE, WARM_CACHE_ROUNDS,
  SERVICE_READY_ATTEMPTS, SERVICE_READY_DELAY, SHOW_STATUS
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
    --no-warm-cache)
      RUN_WARM_PUBLIC_CACHE=0
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

wait_for_service() {
  ready_url="http://127.0.0.1:8000/readyz"
  attempt=1
  echo
  echo "[deploy] waiting for service readiness: $ready_url"
  while [ "$attempt" -le "$SERVICE_READY_ATTEMPTS" ]; do
    if curl --fail --silent --show-error --max-time 3 "$ready_url" >/dev/null 2>&1; then
      echo "[deploy] service ready after $attempt attempt(s)"
      return 0
    fi
    sleep "$SERVICE_READY_DELAY"
    attempt=$((attempt + 1))
  done

  echo "[deploy] service did not become ready after $SERVICE_READY_ATTEMPTS attempts" >&2
  sudo systemctl --no-pager --lines=40 status "$SERVICE_NAME" || true
  return 1
}

if [ ! -d "$APP_DIR" ]; then
  echo "[deploy] app directory not found: $APP_DIR" >&2
  exit 1
fi

cd "$APP_DIR"

if [ -n "$(git status --porcelain)" ]; then
  echo "[deploy] working tree is not clean; commit or stash server-side changes before deployment" >&2
  git status --short >&2
  exit 1
fi

PREVIOUS_COMMIT="$(git rev-parse HEAD)"

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
  if [ "$(git rev-parse HEAD)" != "$PREVIOUS_COMMIT" ]; then
    DEPLOY_UPDATED=1
  fi
fi

if [ "$RUN_REQUIREMENTS" = "1" ]; then
  run "$PYTHON_BIN" -m pip install --break-system-packages -r requirements.txt
fi

if [ "$RUN_APPLY_SCHEMA" = "1" ]; then
  run "$PYTHON_BIN" scripts/apply_postgres_schema.py
  run "$PYTHON_BIN" scripts/cleanup_runtime_state.py --purge-legacy-web-login
fi

if [ "$RUN_PRE_DEPLOY_CHECK" = "1" ]; then
  run "$PYTHON_BIN" scripts/pre_deploy_check.py
fi

if [ "$RUN_NGINX_CHECK" = "1" ]; then
  run sudo nginx -t
  run sudo systemctl reload nginx
fi

if [ "$RESTART_SERVICE" = "1" ]; then
  if [ -f "deploy/systemd/werewolf-stats-import-worker.service" ]; then
    run sudo cp deploy/systemd/werewolf-stats-import-worker.service \
      "/etc/systemd/system/$IMPORT_WORKER_SERVICE.service"
    if [ -f "deploy/systemd/werewolf-stats-maintenance.service" ]; then
      run sudo cp deploy/systemd/werewolf-stats-maintenance.service \
        /etc/systemd/system/werewolf-stats-maintenance.service
      run sudo cp deploy/systemd/werewolf-stats-maintenance.timer \
        /etc/systemd/system/werewolf-stats-maintenance.timer
    fi
    run sudo systemctl daemon-reload
    run sudo systemctl enable "$IMPORT_WORKER_SERVICE"
    if [ -f "/etc/systemd/system/werewolf-stats-maintenance.timer" ]; then
      run sudo systemctl enable --now werewolf-stats-maintenance.timer
    fi
    run sudo systemctl restart "$IMPORT_WORKER_SERVICE"
  fi
  run sudo systemctl restart "$SERVICE_NAME"
  wait_for_service
fi

if [ "$RUN_WARM_PUBLIC_CACHE" = "1" ]; then
  run "$PYTHON_BIN" scripts/warm_public_api_cache.py \
    --base-url "http://127.0.0.1:8000" \
    --rounds "$WARM_CACHE_ROUNDS"
fi

if [ "$SHOW_STATUS" = "1" ]; then
  echo
  echo "[deploy] service status:"
  sudo systemctl --no-pager --lines=20 status "$SERVICE_NAME"
fi

echo
echo "[deploy] done"
trap - EXIT INT TERM HUP
