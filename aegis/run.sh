#!/usr/bin/env bash
# One command: installs deps (first run), builds the console, starts AEGIS on http://localhost:8000
#   ./run.sh           start (reuses the existing database)
#   ./run.sh --reset   start with a fresh database + newly seeded cardholder history
#   ./run.sh --build   rebuild the React console first
set -e
cd "$(dirname "$0")"
if [ -f .env ]; then set -a; . ./.env; set +a; fi   # AWS + AEGIS_* settings
if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -q -r backend/requirements.txt
fi
if [ ! -d frontend/node_modules ]; then (cd frontend && npm install --silent); fi
if [ "$1" == "--reset" ]; then rm -f backend/aegis.db backend/aegis.db-wal backend/aegis.db-shm; echo "database reset"; fi
if [ ! -d frontend/dist ] || [ "$1" == "--build" ]; then (cd frontend && npm run build --silent); fi
cd backend
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
