#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

cleanup() {
  docker compose down -v
}
trap cleanup EXIT

docker compose up -d --build

# basic wait loop for app dependencies already handled by compose healthchecks
sleep 5

# Run e2e tests (activate your venv first, or use: "$ROOT_DIR/.venv/bin/python" -m pytest ...)
python -m pytest tests/test_e2e_integration.py -v
