#!/usr/bin/env bash
# Task runner for the resume screener.  Usage: ./run.sh <command>
set -euo pipefail
cd "$(dirname "$0")"

# The backend port. 8000 is often already in use, so we default to 8001.
PORT="${PORT:-8001}"
PY=".venv/bin/python"

# Load nvm, since a non-interactive shell does not pick it up from .bashrc.
load_node() {
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  # shellcheck disable=SC1091
  [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
  command -v node >/dev/null || { echo "Node is not installed. See the README."; exit 1; }
}

case "${1:-help}" in

  install)
    $PY -m pip install -q -r requirements.txt
    load_node && (cd frontend && npm install)
    echo "Done. Now put your API key in .env, then run: ./run.sh dev"
    ;;

  # Both servers together. Ctrl-C stops both.
  dev)
    load_node
    .venv/bin/uvicorn backend.main:app --reload --port "$PORT" &
    api_pid=$!
    (cd frontend && VITE_API_TARGET="http://localhost:$PORT" npm run dev) &
    ui_pid=$!
    trap 'kill $api_pid $ui_pid 2>/dev/null || true' INT TERM EXIT
    echo ""
    echo "  UI  -> http://localhost:5173"
    echo "  API -> http://localhost:$PORT/docs"
    echo ""
    wait
    ;;

  api)
    .venv/bin/uvicorn backend.main:app --reload --port "$PORT"
    ;;

  ui)
    load_node && (cd frontend && VITE_API_TARGET="http://localhost:$PORT" npm run dev)
    ;;

  test)
    $PY -m pytest -q
    ;;

  build)
    load_node && (cd frontend && npm run build)
    ;;

  # Wipe the database and uploaded files - a fresh demo.
  clean)
    find . -path ./.venv -prune -o -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
    rm -rf .pytest_cache frontend/dist data/app.db
    find data/uploads -type f ! -name .gitkeep -delete 2>/dev/null || true
    echo "Cleaned."
    ;;

  *)
    cat <<'HELP'
Usage: ./run.sh <command>

  install   Install Python and npm dependencies
  dev       Run the API and the UI together   -> http://localhost:5173
  api       Run just the API                  -> http://localhost:8001/docs
  ui        Run just the React UI
  test      Run the test suite
  build     Production build of the frontend
  clean     Delete the database, uploads and caches

Set PORT=... to move the API off 8001.
HELP
    ;;
esac
