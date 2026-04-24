#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-}"
REGION="${REGION:-us-central1}"
ARTIFACT_REPOSITORY="${ARTIFACT_REPOSITORY:-orty}"
SERVICE_ACCOUNT_NAME="${SERVICE_ACCOUNT_NAME:-orty-cloud-run}"
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_EMAIL:-${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com}"
DATABASE_URL_SECRET="${DATABASE_URL_SECRET:-orty-database-url}"
ORTY_SHARED_SECRET_SECRET="${ORTY_SHARED_SECRET_SECRET:-orty-shared-secret}"
INSTANCE_CONNECTION_NAME="${INSTANCE_CONNECTION_NAME:-}"

failures=0

check() {
  local description="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    printf '[ok] %s\n' "$description"
  else
    printf '[missing] %s\n' "$description"
    failures=$((failures + 1))
  fi
}

if [[ -z "${PROJECT_ID}" ]]; then
  echo 'PROJECT_ID is required'
  exit 2
fi

gcloud config set project "${PROJECT_ID}" >/dev/null

for api in run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com sqladmin.googleapis.com aiplatform.googleapis.com; do
  check "API enabled: ${api}" gcloud services list --enabled --filter="config.name=${api}" --format='value(config.name)'
done

check "Artifact Registry repo: ${ARTIFACT_REPOSITORY}" gcloud artifacts repositories describe "${ARTIFACT_REPOSITORY}" --location "${REGION}"
check "Service account: ${SERVICE_ACCOUNT_EMAIL}" gcloud iam service-accounts describe "${SERVICE_ACCOUNT_EMAIL}"
check "Secret exists: ${DATABASE_URL_SECRET}" gcloud secrets describe "${DATABASE_URL_SECRET}"
check "Secret exists: ${ORTY_SHARED_SECRET_SECRET}" gcloud secrets describe "${ORTY_SHARED_SECRET_SECRET}"

if [[ -n "${INSTANCE_CONNECTION_NAME}" ]]; then
  check "Cloud SQL instance connection: ${INSTANCE_CONNECTION_NAME}" gcloud sql instances describe "${INSTANCE_CONNECTION_NAME##*:}"
fi

if [[ "${failures}" -gt 0 ]]; then
  printf '\nPrereq check failed with %d missing item(s).\n' "${failures}"
  exit 1
fi

printf '\nAll checked Google Cloud beta prereqs are present.\n'
