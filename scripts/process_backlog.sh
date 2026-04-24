#!/usr/bin/env bash
# Process Orty bug backlog with Codey
# Usage: ./process_backlog.sh [pending|all]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export ORTY_URL="${ORTY_URL:-http://localhost:8080}"
export CODEY_URL="${CODEY_URL:-http://localhost:8000}"
export ORTY_SECRET="${ORTY_SECRET:-OrtyIAmYourFather}"
export CODEY_API_KEY="${CODEY_API_KEY:-orty-service-key}"
export ALFRED_WORKSPACE="${ALFRED_WORKSPACE:-/home/ortluk/ortluk-hub/Alfred/Alfred}"

python3 "${SCRIPT_DIR}/process_backlog.py" "$@"
