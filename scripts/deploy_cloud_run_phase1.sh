#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID to your Google Cloud project id.}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-orty-api-beta}"
ARTIFACT_REPOSITORY="${ARTIFACT_REPOSITORY:-orty}"
MODEL_BUCKET_NAME="${MODEL_BUCKET_NAME:-ortypublic-models}"
MODEL_VOLUME_NAME="${MODEL_VOLUME_NAME:-orty-models}"
MODEL_MOUNT_PATH="${MODEL_MOUNT_PATH:-/models}"
IMAGE_TAG="${IMAGE_TAG:-$(date +%Y%m%d-%H%M%S)}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPOSITORY}/${SERVICE_NAME}:${IMAGE_TAG}"
DATABASE_URL_SECRET="${DATABASE_URL_SECRET:?Set DATABASE_URL_SECRET to the Secret Manager secret name for DATABASE_URL.}"
DATABASE_URL_SECRET_VERSION="${DATABASE_URL_SECRET_VERSION:-latest}"
ORTY_SHARED_SECRET_SECRET="${ORTY_SHARED_SECRET_SECRET:-orty-shared-secret}"
ORTY_SHARED_SECRET_VERSION="${ORTY_SHARED_SECRET_VERSION:-latest}"
ORTY_ADMIN_SECRET_SECRET="${ORTY_ADMIN_SECRET_SECRET:-orty-admin-secret}"
ORTY_ADMIN_SECRET_VERSION="${ORTY_ADMIN_SECRET_VERSION:-latest}"
VERTEX_AI_LOCATION="${VERTEX_AI_LOCATION:-us-central1}"
VERTEX_AI_MODEL_ID="${VERTEX_AI_MODEL_ID:-publishers/google/models/gemini-2.5-flash}"
ALLOW_UNAUTHENTICATED="${ALLOW_UNAUTHENTICATED:-true}"
CREATE_ARTIFACT_REPOSITORY="${CREATE_ARTIFACT_REPOSITORY:-true}"
APPLY_SCHEMA="${APPLY_SCHEMA:-true}"
RUN_SMOKE_TESTS="${RUN_SMOKE_TESTS:-true}"
MEMORY="${MEMORY:-1Gi}"
CPU="${CPU:-1}"
CONCURRENCY="${CONCURRENCY:-8}"
TIMEOUT="${TIMEOUT:-60s}"
MIN_INSTANCES="${MIN_INSTANCES:-0}"
MAX_INSTANCES="${MAX_INSTANCES:-3}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-}"
INSTANCE_CONNECTION_NAME="${INSTANCE_CONNECTION_NAME:-}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-${REPO_ROOT}/.venv/bin/python}"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

assumption() {
  printf '[assumption] %s\n' "$*"
}

assumption "Cloud Run should use Vertex AI as the primary inference path."
assumption "The deployed container should not depend on Ollama or any local inference process."
assumption "DATABASE_URL, ORTY_SHARED_SECRET, and ORTY_ADMIN_SECRET already exist in Secret Manager."
assumption "If DATABASE_URL uses the Cloud SQL socket path, INSTANCE_CONNECTION_NAME should be set for Cloud Run attachment."
assumption "If deployment fails after traffic was serving, rollback should target the previous ready revision."

gcloud config set project "${PROJECT_ID}" >/dev/null
PREVIOUS_REVISION="$(gcloud run services describe "${SERVICE_NAME}" --region "${REGION}" --format='value(status.latestReadyRevisionName)' 2>/dev/null || true)"

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com storage.googleapis.com >/dev/null

if ! gcloud storage buckets describe "gs://${MODEL_BUCKET_NAME}" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${MODEL_BUCKET_NAME}" \
    --location="${REGION}" \
    --uniform-bucket-level-access
fi

if [[ -n "${SERVICE_ACCOUNT}" ]]; then
  gcloud storage buckets add-iam-policy-binding "gs://${MODEL_BUCKET_NAME}" \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/storage.objectAdmin"
fi

if [[ "${CREATE_ARTIFACT_REPOSITORY}" == "true" ]]; then
  if ! gcloud artifacts repositories describe "${ARTIFACT_REPOSITORY}" --location "${REGION}" >/dev/null 2>&1; then
    gcloud artifacts repositories create "${ARTIFACT_REPOSITORY}" \
      --repository-format=docker \
      --location="${REGION}" \
      --description="Orty release images"
  fi
fi

if [[ "${APPLY_SCHEMA}" == "true" ]]; then
  DATABASE_URL="$(gcloud secrets versions access "${DATABASE_URL_SECRET_VERSION}" --secret="${DATABASE_URL_SECRET}")"
  SCHEMA_PROXY_PID=""
  if [[ "${DATABASE_URL}" =~ host=/cloudsql/([^?]+) ]]; then
    INSTANCE_CONNECTION_NAME="${BASH_REMATCH[1]}"
    CLOUD_SQL_PROXY_BIN="${CLOUD_SQL_PROXY_BIN:-${HOME}/bin/cloud-sql-proxy}"
    if [[ ! -x "${CLOUD_SQL_PROXY_BIN}" ]]; then
      printf '[deploy] cloud-sql-proxy not found at %s
' "${CLOUD_SQL_PROXY_BIN}" >&2
      exit 1
    fi

    CLOUD_SQL_PROXY_PORT="${CLOUD_SQL_PROXY_PORT:-5432}"
    "${CLOUD_SQL_PROXY_BIN}" "${INSTANCE_CONNECTION_NAME}" --address 127.0.0.1 --port "${CLOUD_SQL_PROXY_PORT}" --quiet >/tmp/orty-cloud-sql-proxy.log 2>&1 &
    SCHEMA_PROXY_PID="$!"
    trap 'if [[ -n "${SCHEMA_PROXY_PID}" ]]; then kill "${SCHEMA_PROXY_PID}" >/dev/null 2>&1 || true; fi' EXIT

    for _ in {1..30}; do
      if (echo > /dev/tcp/127.0.0.1/${CLOUD_SQL_PROXY_PORT}) >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done

    DATABASE_URL="$(python3 - <<'PY' "${DATABASE_URL}" "${CLOUD_SQL_PROXY_PORT}"
import sys
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

raw_url = sys.argv[1]
port = sys.argv[2]
parts = urlsplit(raw_url)
query_items = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != 'host']
netloc = parts.netloc
if '@' in netloc:
    auth, _ = netloc.split('@', 1)
    netloc = f'{auth}@127.0.0.1:{port}'
else:
    netloc = f'127.0.0.1:{port}'
print(urlunsplit((parts.scheme, netloc, parts.path, urlencode(query_items), parts.fragment)))
PY
)"
  fi

  DATABASE_URL="${DATABASE_URL}" "${PYTHON_BIN}" "${SCRIPT_DIR}/apply_postgres_schema.py"
  if [[ -n "${SCHEMA_PROXY_PID}" ]]; then
    kill "${SCHEMA_PROXY_PID}" >/dev/null 2>&1 || true
  fi
  trap - EXIT
fi

gcloud builds submit --tag "${IMAGE}" "${REPO_ROOT}"

deploy_args=(
  gcloud run deploy "${SERVICE_NAME}"
  --image "${IMAGE}"
  --region "${REGION}"
  --platform managed
  --port 8080
  --memory "${MEMORY}"
  --cpu "${CPU}"
  --concurrency "${CONCURRENCY}"
  --timeout "${TIMEOUT}"
  --min-instances "${MIN_INSTANCES}"
  --max-instances "${MAX_INSTANCES}"
  --use-http2
  --execution-environment gen2
  --set-env-vars "ORTY_DEPLOYMENT_PROFILE=cloud_run_interactive,LLM_PROVIDER=vertex_ai,ENABLE_CLOUD_FALLBACK=false,ENABLE_PARALLEL_PROVIDER_RACE=false,ENABLE_BOT_CONTROL_SURFACE=false,ALLOW_LEGACY_CLIENT_HEADERS=false,VERTEX_AI_PROJECT_ID=${PROJECT_ID},VERTEX_AI_LOCATION=${VERTEX_AI_LOCATION},VERTEX_AI_MODEL_ID=${VERTEX_AI_MODEL_ID},ORTY_ALFRED_CLIENT_KEY=${ORTY_ALFRED_CLIENT_KEY:-alfred-android},ORTY_MODEL_STORAGE_ROOT=${MODEL_MOUNT_PATH}"
  --set-secrets "DATABASE_URL=${DATABASE_URL_SECRET}:${DATABASE_URL_SECRET_VERSION},ORTY_SHARED_SECRET=${ORTY_SHARED_SECRET_SECRET}:${ORTY_SHARED_SECRET_VERSION},ORTY_ADMIN_SECRET=${ORTY_ADMIN_SECRET_SECRET}:${ORTY_ADMIN_SECRET_VERSION}"
  --add-volume "name=${MODEL_VOLUME_NAME},type=cloud-storage,bucket=${MODEL_BUCKET_NAME}"
  --add-volume-mount "volume=${MODEL_VOLUME_NAME},mount-path=${MODEL_MOUNT_PATH}"
)

if [[ -n "${SERVICE_ACCOUNT}" ]]; then
  deploy_args+=(--service-account "${SERVICE_ACCOUNT}")
fi

if [[ -n "${INSTANCE_CONNECTION_NAME}" ]]; then
  deploy_args+=(--add-cloudsql-instances "${INSTANCE_CONNECTION_NAME}")
fi

if [[ "${ALLOW_UNAUTHENTICATED}" == "true" ]]; then
  deploy_args+=(--allow-unauthenticated)
else
  deploy_args+=(--no-allow-unauthenticated)
fi

"${deploy_args[@]}"

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" --region "${REGION}" --format='value(status.url)')"
printf '\nDeployed %s to %s\n' "${SERVICE_NAME}" "${SERVICE_URL}"

if [[ "${RUN_SMOKE_TESTS}" == "true" ]]; then
  ORTY_SHARED_SECRET="$(gcloud secrets versions access "${ORTY_SHARED_SECRET_VERSION}" --secret="${ORTY_SHARED_SECRET_SECRET}")"
  SERVICE_URL="${SERVICE_URL}" ORTY_SHARED_SECRET="${ORTY_SHARED_SECRET}" bash "${SCRIPT_DIR}/smoke_cloud_run_beta.sh"
fi

printf '\nRollback:\n'
if [[ -n "${PREVIOUS_REVISION}" ]]; then
  printf 'PROJECT_ID=%q REGION=%q SERVICE_NAME=%q TARGET_REVISION=%q bash %q\n' \
    "${PROJECT_ID}" "${REGION}" "${SERVICE_NAME}" "${PREVIOUS_REVISION}" "${SCRIPT_DIR}/rollback_cloud_run.sh"
else
  printf 'No previous ready revision was found; rollback would require redeploying a known-good image.\n'
fi
