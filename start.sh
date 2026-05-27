#!/bin/bash
# OKX Token Sourcing Dashboard — startup script
set -e

cd "$(dirname "$0")"

# Install dependencies if not already installed
if ! python -c "import fastapi" &>/dev/null; then
  echo "Installing dependencies..."
  pip install -r requirements.txt -q
fi

PORT=${PORT:-8080}
echo ""
echo "  OKX Token Sourcing Dashboard"
echo "  ──────────────────────────────"
echo "  Open: http://localhost:$PORT"
echo ""

uvicorn app:app --host 0.0.0.0 --port "$PORT" --log-level info
