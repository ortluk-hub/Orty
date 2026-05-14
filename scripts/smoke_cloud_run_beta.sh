#!/usr/bin/env bash
set -euo pipefail

SERVICE_URL="${SERVICE_URL:?Set SERVICE_URL to the deployed Cloud Run URL.}"
ORTY_SHARED_SECRET="${ORTY_SHARED_SECRET:?Set ORTY_SHARED_SECRET for admin smoke checks.}"
SMOKE_CLIENT_NAME="${SMOKE_CLIENT_NAME:-Cloud Run Smoke Client}"

json_field() {
  python3 -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"
}

echo '[smoke] GET /health'
curl -fsS "${SERVICE_URL}/health" >/dev/null

echo '[smoke] POST /v1/clients'
CREATE_PAYLOAD="$(python3 -c 'import json,sys; print(json.dumps({"name": sys.argv[1], "preferences": {"smoke_test": True}}))' "${SMOKE_CLIENT_NAME}")"
CREATE_RESPONSE="$(curl -fsS -X POST "${SERVICE_URL}/v1/clients" \
  -H "Content-Type: application/json" \
  -H "x-orty-secret: ${ORTY_SHARED_SECRET}" \
  -d "${CREATE_PAYLOAD}")"
CLIENT_ID="$(printf '%s' "${CREATE_RESPONSE}" | json_field client_id)"
CLIENT_TOKEN="$(printf '%s' "${CREATE_RESPONSE}" | json_field client_token)"

echo '[smoke] POST /v1/auth/token'
TOKEN_PAYLOAD="$(python3 -c 'import json,sys; print(json.dumps({"client_id": sys.argv[1], "client_token": sys.argv[2]}))' "${CLIENT_ID}" "${CLIENT_TOKEN}")"
TOKEN_RESPONSE="$(curl -fsS -X POST "${SERVICE_URL}/v1/auth/token" \
  -H 'Content-Type: application/json' \
  -d "${TOKEN_PAYLOAD}")"
ACCESS_TOKEN="$(printf '%s' "${TOKEN_RESPONSE}" | json_field access_token)"

echo '[smoke] GET /v1/auth/me'
curl -fsS "${SERVICE_URL}/v1/auth/me" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" >/dev/null

echo '[smoke] POST /chat'
CHAT_PAYLOAD='{"message":"Reply with ok only.","persist":false}'
CHAT_RESPONSE="$(curl -fsS -X POST "${SERVICE_URL}/chat" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -d "${CHAT_PAYLOAD}")"
printf '%s' "${CHAT_RESPONSE}" | python3 -c 'import json,sys; payload=json.load(sys.stdin); assert payload.get("reply"), "chat reply missing"; assert payload.get("conversation_id"), "conversation_id missing"'

echo '[smoke] core auth/chat checks passed'
