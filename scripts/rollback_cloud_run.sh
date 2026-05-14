#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID to your Google Cloud project id.}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:?Set SERVICE_NAME to the Cloud Run service name.}"
TARGET_REVISION="${TARGET_REVISION:?Set TARGET_REVISION to the previous ready revision.}"

gcloud config set project "${PROJECT_ID}" >/dev/null
gcloud run services update-traffic "${SERVICE_NAME}" \
  --region "${REGION}" \
  --to-revisions "${TARGET_REVISION}=100"

echo "Rolled ${SERVICE_NAME} back to revision ${TARGET_REVISION}."
