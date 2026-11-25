#!/usr/bin/env bash
set -euo pipefail

# Deploy lifecycle script for COMPANY_OS_PY_BE (FastAPI/Uvicorn)
# Usage: ./deploy.sh <uat|prod> <start|stop|restart|refresh|status>
#        ./deploy.sh <start|stop|restart|refresh|status> <uat|prod>

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"
cd "$ROOT_DIR"

# Default environment
ENV="${1:-uat}"
ACTION="${2:-start}"

# Allow either order: ./deploy.sh uat start  OR  ./deploy.sh start uat
if [[ -n "${2:-}" ]] && [[ ! "$ENV" =~ ^(uat|prod)$ ]]; then
    ACTION="$ENV"
    ENV="$2"
fi

case "$ENV" in
    uat|prod) ;;
    *)
        echo "ERROR: Environment must be 'uat' or 'prod', got '$ENV'" >&2
        exit 1
        ;;
esac

ENV_FILE="$SCRIPT_DIR/.env.$ENV"

# Validate environment file exists
if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: Environment file '$ENV_FILE' not found." >&2
    echo "Create it from .env.uat.example or .env.prod.example" >&2
    exit 1
fi

# Load environment variables
set -a
source "$ENV_FILE"
set +a

# Validate PORT
if [[ -z "${PORT:-}" ]]; then
    echo "ERROR: PORT is not defined in $ENV_FILE" >&2
    exit 1
fi

PID_FILE="$SCRIPT_DIR/.deploy.$ENV.pid"
LOG_FILE="$SCRIPT_DIR/.deploy.$ENV.log"

# Helper: get PID from pidfile only (reliable, no lsof needed)
get_pid() {
    if [[ -f "$PID_FILE" ]]; then
        local pid
        pid=$(cat "$PID_FILE" 2>/dev/null)
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
        rm -f "$PID_FILE"
    fi
    echo ""
    return 1
}

stop_if_running() {
    local pid
    pid=$(get_pid)
    if [[ -n "$pid" ]]; then
        echo "  Stopping process $pid (running on port $PORT)..."
        kill "$pid" 2>/dev/null || true
        for _ in {1..10}; do
            if ! kill -0 "$pid" 2>/dev/null; then
                break
            fi
            sleep 0.5
        done
        if kill -0 "$pid" 2>/dev/null; then
            echo "  Warning: process $pid did not stop gracefully, killing..."
            kill -9 "$pid" 2>/dev/null || true
            sleep 1
        fi
        rm -f "$PID_FILE"
        echo "  Stopped."
    fi
}

cmd_start() {
    echo "Starting $ENV environment on port $PORT..."
    stop_if_running

    local cmd
    if [[ "$ENV" == "uat" ]]; then
        cmd="uv run uvicorn app.main:app --reload --host 0.0.0.0 --port $PORT"
    else
        cmd="uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2"
    fi

    echo "  Running: $cmd"
    nohup bash -c "$cmd" > "$LOG_FILE" 2>&1 &
    local pid=$!
    echo "$pid" > "$PID_FILE"

    echo "  Started (PID: $pid). Waiting for server to be ready..."
    sleep 2

    if curl -sf "http://127.0.0.1:$PORT/api/health" > /dev/null 2>&1; then
        echo "  Health check passed: $(curl -sf "http://127.0.0.1:$PORT/api/health" | tr -d '\n')"
    else
        echo "  Warning: Health check failed. Check $LOG_FILE"
    fi
    echo "  Started."
}

cmd_stop() {
    echo "Stopping $ENV environment (port $PORT)..."
    stop_if_running
    echo "  Stopped."
}

cmd_restart() {
    echo "Restarting $ENV environment..."
    cmd_stop
    cmd_start
}

cmd_refresh() {
    echo "Refreshing dependencies..."
    uv sync
    echo "  Dependencies updated."
    cmd_restart
}

cmd_status() {
    local pid
    pid=$(get_pid)

    if [[ -n "$pid" ]]; then
        echo "Status: RUNNING"
        echo "  PID: $pid"
        echo "  Environment: $ENV"
        echo "  Port: $PORT"
        echo "  Log (last 5 lines):"
        tail -5 "$LOG_FILE" 2>/dev/null | while read -r line; do echo "    $line"; done
    else
        echo "Status: STOPPED"
        echo "  Environment: $ENV"
        echo "  Port: $PORT"
        echo "  Log (last 5 lines):"
        tail -5 "$LOG_FILE" 2>/dev/null | while read -r line; do echo "    $line"; done
    fi
}

case "$ACTION" in
    start)
        cmd_start
        ;;
    stop)
        cmd_stop
        ;;
    restart)
        cmd_restart
        ;;
    refresh)
        cmd_refresh
        ;;
    status)
        cmd_status
        ;;
    *)
        echo "ERROR: Unknown action '$ACTION'" >&2
        echo "Usage: $0 <uat|prod> [start|stop|restart|refresh|status]" >&2
        exit 1
        ;;
esac
