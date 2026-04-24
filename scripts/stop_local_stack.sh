#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="/tmp/orty-local-stack"
ORTY_PID_FILE="${STATE_DIR}/orty.pid"
CLOUDFLARED_PID_FILE="${STATE_DIR}/cloudflared.pid"

stop_pid_file() {
  local pid_file="$1"
  if [[ ! -f "${pid_file}" ]]; then
    return 0
  fi
  local pid
  pid="$(cat "${pid_file}")"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
    kill "${pid}" 2>/dev/null || true
  fi
  rm -f "${pid_file}"
}

stop_pid_file "${CLOUDFLARED_PID_FILE}"
stop_pid_file "${ORTY_PID_FILE}"

echo "Stopped Orty local stack."
