# Orty Google Cloud Beta Setup

This runbook covers the Google Cloud side required before the first real Orty beta deploy from `orty-server`.

It assumes:
- Orty source is in `/home/ortluk/ortluk-hub/orty/Orty`
- production artifact is a Cloud Run container image
- Cloud Run uses Vertex AI as the primary inference path
- Orty persistence uses PostgreSQL through `DATABASE_URL`
- secrets are stored in Secret Manager

This document is intentionally biased toward the smallest reliable setup for beta.

## 1. Choose values once

Set these shell variables in the `orty-server` shell before doing setup:

```bash
export PROJECT_ID="your-gcp-project-id"
export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
export REGION="us-central1"
export SERVICE_NAME="orty-api-beta"
export ARTIFACT_REPOSITORY="orty"
export SERVICE_ACCOUNT_NAME="orty-cloud-run"
export SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
export DATABASE_URL_SECRET="orty-database-url"
export ORTY_SHARED_SECRET_SECRET="orty-shared-secret"
```

If you don't already have a project, create one in the Google Cloud console first.

## 2. Authenticate and target the project

```bash
gcloud auth login
gcloud config set project "$PROJECT_ID"
```

## 3. Enable required APIs

These are the minimum Google services Orty needs for the beta path:

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  sqladmin.googleapis.com \
  aiplatform.googleapis.com
```

Why:
- `run.googleapis.com`: Cloud Run deploy and serving
- `cloudbuild.googleapis.com`: builds the container image
- `artifactregistry.googleapis.com`: stores the release image
- `secretmanager.googleapis.com`: stores `DATABASE_URL` and `ORTY_SHARED_SECRET`
- `sqladmin.googleapis.com`: Cloud SQL administration
- `aiplatform.googleapis.com`: Vertex AI inference

## 4. Create the Cloud Run service account

Use a dedicated service account instead of the default one:

```bash
gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
  --display-name="Orty Cloud Run"
```

## 5. Grant the runtime service account the minimum beta roles

Grant these roles to the Cloud Run runtime service account:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
  --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
  --role="roles/cloudsql.client"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
  --role="roles/secretmanager.secretAccessor"
```

Why:
- `roles/aiplatform.user`: allows Vertex AI generative model use
- `roles/cloudsql.client`: required when Cloud Run connects to Cloud SQL
- `roles/secretmanager.secretAccessor`: lets the service read secrets at runtime

Official references:
- Cloud Run deploy/identity and required roles: [Cloud Run IAM roles](https://docs.cloud.google.com/run/docs/reference/iam/roles)
- Cloud Run to Cloud SQL: [Connect from Cloud Run to Cloud SQL for PostgreSQL](https://docs.cloud.google.com/sql/docs/postgres/connect-run)
- Vertex AI generative access: [Generative AI access control](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/access-control)
- Secret Manager IAM: [Secret Manager access control](https://cloud.google.com/secret-manager/docs/access-control)

## 6. Make sure the deployer account can deploy

The user account running the deploy from `orty-server` needs permissions too.

For a least-privilege deploy path, the deployer should have:
- `roles/run.developer`
- `roles/iam.serviceAccountUser` on `${SERVICE_ACCOUNT_EMAIL}`
- write access needed to build/push images and manage bootstrap resources

For first bootstrap, the simplest practical option is to use a project owner/editor account once, then tighten later.

## 7. Create the Artifact Registry repository

```bash
gcloud artifacts repositories create "$ARTIFACT_REPOSITORY" \
  --repository-format=docker \
  --location="$REGION" \
  --description="Orty release images"
```

Cloud Run supports multiple image sources, but Google recommends Artifact Registry for container images: [Deploying container images to Cloud Run](https://docs.cloud.google.com/run/docs/deploying).

## 8. Create the PostgreSQL database

For the beta path, use Cloud SQL for PostgreSQL unless you already have another managed PostgreSQL endpoint you trust.

Example bootstrap:

```bash
export DB_INSTANCE="orty-beta-pg"
export DB_NAME="orty"
export DB_USER="orty"
export DB_PASSWORD="choose-a-strong-password"

gcloud sql instances create "$DB_INSTANCE" \
  --database-version=POSTGRES_16 \
  --cpu=1 \
  --memory=3840MiB \
  --region="$REGION" \
  --storage-size=20GB

gcloud sql databases create "$DB_NAME" \
  --instance="$DB_INSTANCE"

gcloud sql users create "$DB_USER" \
  --instance="$DB_INSTANCE" \
  --password="$DB_PASSWORD"
```

For the first beta cut, the simplest connection path is usually Cloud SQL public IP plus Cloud Run's Cloud SQL integration. If you later want private IP or VPC routing, add that as a follow-on hardening slice.

## 9. Build the `DATABASE_URL`

Get the instance connection name:

```bash
export INSTANCE_CONNECTION_NAME="$(gcloud sql instances describe "$DB_INSTANCE" --format='value(connectionName)')"
```

For this beta path, use the Cloud SQL Unix socket path in the DSN host portion:

```bash
export DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@/${DB_NAME}?host=/cloudsql/${INSTANCE_CONNECTION_NAME}"
```

Important:
- this assumes the Cloud Run service is configured with the Cloud SQL connection
- Orty itself just reads `DATABASE_URL`; the Cloud Run service wiring supplies the actual socket mount

## 10. Create the required secrets

Generate or choose the Orty admin secret and store both secrets in Secret Manager:

```bash
openssl rand -hex 32
```

Use that output as `ORTY_SHARED_SECRET`, then create secrets:

```bash
printf '%s' "$DATABASE_URL" | gcloud secrets create "$DATABASE_URL_SECRET" --data-file=-
printf '%s' "$ORTY_SHARED_SECRET" | gcloud secrets create "$ORTY_SHARED_SECRET_SECRET" --data-file=-
```

If the secrets already exist, add new versions instead:

```bash
printf '%s' "$DATABASE_URL" | gcloud secrets versions add "$DATABASE_URL_SECRET" --data-file=-
printf '%s' "$ORTY_SHARED_SECRET" | gcloud secrets versions add "$ORTY_SHARED_SECRET_SECRET" --data-file=-
```

## 11. Connect Cloud Run to Cloud SQL

The deploy script already handles env vars and secrets, but Cloud Run also needs the Cloud SQL connection itself.

Current repo note:
- the repo deploy script assumes `DATABASE_URL` exists and applies the schema automatically
- if you are using Cloud SQL sockets, make sure the deployed service is configured with the Cloud SQL instance connection

If you deploy manually in the console, add the Cloud SQL connection there.
If you deploy by `gcloud`, you should add:

```bash
--add-cloudsql-instances "$INSTANCE_CONNECTION_NAME"
```

If you want the repo deploy script to carry that too, add `INSTANCE_CONNECTION_NAME` to the deploy environment before running it and update the script if needed.

## 12. Preflight check before first deploy

From `orty-server`:

```bash
cd /home/ortluk/ortluk-hub/orty/Orty
bash scripts/check_gcp_beta_prereqs.sh
```

This script is non-destructive. It checks for the project config, APIs, repo, service account, and required secrets.

## 13. Run the first deploy

From `orty-server`:

```bash
cd /home/ortluk/ortluk-hub/orty/Orty
export PROJECT_ID="$PROJECT_ID"
export REGION="$REGION"
export SERVICE_NAME="$SERVICE_NAME"
export ARTIFACT_REPOSITORY="$ARTIFACT_REPOSITORY"
export SERVICE_ACCOUNT="$SERVICE_ACCOUNT_EMAIL"
export DATABASE_URL_SECRET="$DATABASE_URL_SECRET"
export ORTY_SHARED_SECRET_SECRET="$ORTY_SHARED_SECRET_SECRET"
export INSTANCE_CONNECTION_NAME="$INSTANCE_CONNECTION_NAME"
bash scripts/deploy_cloud_run_phase1.sh
```

If the deploy script does not yet wire `--add-cloudsql-instances`, add it before the first real deploy.

## 14. Verify the deployed service

The deploy script will run the repo smoke test if `RUN_SMOKE_TESTS=true`.

Manual core checks:
- `GET /health`
- `POST /v1/clients`
- `POST /v1/auth/token`
- `GET /v1/auth/me`
- `POST /chat`

Then verify Alfred against the deployed URL on-device.

## 15. Roll back if needed

If the deploy output prints a previous ready revision, roll back traffic with:

```bash
PROJECT_ID="$PROJECT_ID" \
REGION="$REGION" \
SERVICE_NAME="$SERVICE_NAME" \
TARGET_REVISION="the_previous_ready_revision" \
bash scripts/rollback_cloud_run.sh
```

## Common first-deploy failure points

- Vertex AI API enabled, but the Cloud Run service account lacks `roles/aiplatform.user`
- Cloud Run can read secrets, but the deployer account cannot attach the service account
- `DATABASE_URL` exists, but Cloud Run is not attached to the Cloud SQL instance
- Artifact Registry exists, but the deployer account or Cloud Build path lacks access
- The project is right, but the region is inconsistent across Cloud Run, Artifact Registry, and Cloud SQL

## Practical beta recommendation

For the first real cut:
- use one project
- use one region
- use one Cloud SQL Postgres instance
- use one dedicated Cloud Run service account
- keep Cloud Run on Vertex-first inference only
- leave Ollama and local inference out of the production container entirely
