#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ALFRED_LOCAL_PROPERTIES_DEFAULT="/home/ortluk/ortluk-hub/Alfred/Alfred/local.properties"
STATE_DIR="/tmp/orty-local-stack"
ORTY_PID_FILE="${STATE_DIR}/orty.pid"
CLOUDFLARED_PID_FILE="${STATE_DIR}/cloudflared.pid"
ORTY_LOG_FILE="${STATE_DIR}/orty.log"
CLOUDFLARED_LOG_FILE="${STATE_DIR}/cloudflared.log"
TUNNEL_URL_FILE="${STATE_DIR}/tunnel-url.txt"

ORTY_HOST="${ORTY_HOST:-127.0.0.1}"
ORTY_PORT="${ORTY_PORT:-8081}"
ORTY_URL="http://${ORTY_HOST}:${ORTY_PORT}"
HEALTH_URL="${ORTY_URL}/health"
HOMEPAGE_URL="${ORTY_URL}/homepage"
CLOUDFLARED_BIN="${CLOUDFLARED_BIN:-/tmp/cloudflared}"
ORTY_PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
SYNC_ALFRED=0

resolve_lan_url() {
  local port="$1"
  local lan_ip=""
  lan_ip="$(hostname -I 2>/dev/null | tr ' ' '\n' | rg -m 1 '^(10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.|192\.168\.)' || true)"
  if [[ -z "${lan_ip}" ]]; then
    return 1
  fi
  printf 'http://%s:%s\n' "${lan_ip}" "${port}"
}

for arg in "$@"; do
  case "${arg}" in
    --sync-alfred)
      SYNC_ALFRED=1
      ;;
    *)
      echo "Unknown argument: ${arg}" >&2
      exit 1
      ;;
  esac
done

mkdir -p "${STATE_DIR}"

require_bin() {
  local path="$1"
  local label="$2"
  if [[ ! -x "${path}" ]]; then
    echo "Missing ${label}: ${path}" >&2
    exit 1
  fi
}

is_pid_running() {
  local pid_file="$1"
  [[ -f "${pid_file}" ]] || return 1
  local pid
  pid="$(cat "${pid_file}")"
  [[ -n "${pid}" ]] || return 1
  kill -0 "${pid}" 2>/dev/null
}

wait_for_http() {
  local url="$1"
  local attempts="${2:-20}"
  local delay_seconds="${3:-1}"
  for _ in $(seq 1 "${attempts}"); do
    if curl -fsS --connect-timeout 2 "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep "${delay_seconds}"
  done
  return 1
}

extract_tunnel_url() {
  if [[ ! -f "${CLOUDFLARED_LOG_FILE}" ]]; then
    return 1
  fi
  rg -o "https://[A-Za-z0-9.-]+\\.trycloudflare\\.com" -m 1 "${CLOUDFLARED_LOG_FILE}" 2>/dev/null
}

require_bin "${ORTY_PYTHON_BIN}" "Orty virtualenv python"
require_bin "${CLOUDFLARED_BIN}" "cloudflared"

if ! is_pid_running "${ORTY_PID_FILE}"; then
  : > "${ORTY_LOG_FILE}"
  (
    cd "${ROOT_DIR}"
    "${ORTY_PYTHON_BIN}" -m hypercorn service.api:app --bind "${ORTY_HOST}:${ORTY_PORT}" --worker-class asyncio --access-logfile - --error-logfile -
  ) >"${ORTY_LOG_FILE}" 2>&1 < /dev/null &
  echo $! > "${ORTY_PID_FILE}"
fi

if ! wait_for_http "${HEALTH_URL}" 20 1; then
  echo "Orty did not become healthy at ${HEALTH_URL}" >&2
  echo "Log: ${ORTY_LOG_FILE}" >&2
  exit 1
fi

if ! is_pid_running "${CLOUDFLARED_PID_FILE}"; then
  : > "${CLOUDFLARED_LOG_FILE}"
  "${CLOUDFLARED_BIN}" tunnel --url "${ORTY_URL}" --no-autoupdate >"${CLOUDFLARED_LOG_FILE}" 2>&1 < /dev/null &
  echo $! > "${CLOUDFLARED_PID_FILE}"
fi

TUNNEL_URL=""
LAN_URL=""
for _ in $(seq 1 20); do
  if TUNNEL_URL="$(extract_tunnel_url)"; then
    printf '%s\n' "${TUNNEL_URL}" > "${TUNNEL_URL_FILE}"
    break
  fi
  sleep 1
done

LAN_URL="$(resolve_lan_url "${ORTY_PORT}" || true)"

echo "Orty health: ${HEALTH_URL}"
echo "Orty homepage: ${HOMEPAGE_URL}"
if [[ -n "${TUNNEL_URL}" ]]; then
  if [[ "${SYNC_ALFRED}" == "1" && -f "${ALFRED_LOCAL_PROPERTIES_DEFAULT}" ]]; then
    if rg -q '^orty\.base\.url=' "${ALFRED_LOCAL_PROPERTIES_DEFAULT}"; then
      perl -0pi -e 's/^orty\.base\.url=.*/orty.base.url='"${TUNNEL_URL//\//\\/}"'/m' "${ALFRED_LOCAL_PROPERTIES_DEFAULT}"
    else
      printf '\norty.base.url=%s\n' "${TUNNEL_URL}" >> "${ALFRED_LOCAL_PROPERTIES_DEFAULT}"
    fi
    if [[ -n "${LAN_URL}" ]]; then
      if rg -q '^orty\.lan\.base\.url=' "${ALFRED_LOCAL_PROPERTIES_DEFAULT}"; then
        perl -0pi -e 's/^orty\.lan\.base\.url=.*/orty.lan.base.url='"${LAN_URL//\//\\/}"'/m' "${ALFRED_LOCAL_PROPERTIES_DEFAULT}"
      else
        printf 'orty.lan.base.url=%s\n' "${LAN_URL}" >> "${ALFRED_LOCAL_PROPERTIES_DEFAULT}"
      fi
    fi
    echo "Synced Alfred local.properties: ${ALFRED_LOCAL_PROPERTIES_DEFAULT}"
  fi
  echo "Cloudflare URL: ${TUNNEL_URL}"
else
  echo "Cloudflare URL: unavailable yet"
fi
if [[ -n "${LAN_URL}" ]]; then
  echo "LAN URL: ${LAN_URL}"
fi
echo "Orty log: ${ORTY_LOG_FILE}"
echo "Cloudflared log: ${CLOUDFLARED_LOG_FILE}"
