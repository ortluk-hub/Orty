# Orty Cloud Run Phase 1

This document defines the first Cloud Run cutover for Orty's interactive Alfred path.

## Scope

Phase 1 is intentionally narrow:

- Stable public HTTPS URL for Orty
- Public interactive APIs: `/health`, `/chat`, `/v1/auth/*`, `/v1/clients`, `/v1/clients/register`, `/v1/memory/*`, `/v1/stt/*`, `/v1/tts/*`
- Vertex-first response path for user-facing chat
- No local Ollama dependency inside the deployed container
- Explicitly disabled in-process `/v1/bots` control surface

This phase maps to deployment marker D1 in [docs/DEPLOYMENT_ROADMAP.md](docs/DEPLOYMENT_ROADMAP.md).

Out of scope for Phase 1:

- Durable storage migration off SQLite
- Codey migration
- Long-running supervisor bot execution on Cloud Run services
- Shared-filesystem assumptions between Orty and Codey

## Deployment Profile

Set:

```bash
ORTY_DEPLOYMENT_PROFILE=cloud_run_interactive
```

This profile defaults `ENABLE_BOT_CONTROL_SURFACE=false`, so `/v1/bots` returns `503` instead of pretending in-process bot orchestration is safe on Cloud Run.

## Deployment Assumptions

This deployment path assumes:

- `DATABASE_URL` is stored in Secret Manager and points at a reachable PostgreSQL instance
- Vertex AI credentials come from the Cloud Run service account, not a local model process inside the container
- `ORTY_SHARED_SECRET` is stored in Secret Manager
- `ORTY_ALFRED_CLIENT_KEY` is set as a Cloud Run environment variable for Alfred client registration
- Cloud Run is configured for HTTP/2 end-to-end so streaming and model download traffic stay on the h2c path
- The container entrypoint uses an h2c-capable ASGI server (`Hypercorn`); plain `uvicorn` will 502 under Cloud Run HTTP/2
- A Cloud Storage bucket is mounted at `/models` so GGUF uploads persist without rebuilding the container
- The default deploy script provisions `gs://ortypublic-models` for the mounted model volume
- `/v1/bots` remains disabled on Cloud Run

Until D1 exits, treat Cloud Run as the beta cutover target, not as a finished production platform.

## Automated Operator Flow

Google-side operator setup lives in [`docs/GCP_BETA_SETUP.md`](docs/GCP_BETA_SETUP.md).

Use the checked-in scripts from the official repo on `orty-server`:

1. `python3 scripts/apply_postgres_schema.py`
2. `bash scripts/deploy_cloud_run_phase1.sh`
   Set `INSTANCE_CONNECTION_NAME` when using Cloud SQL socket connections.
3. `bash scripts/smoke_cloud_run_beta.sh`
4. `bash scripts/rollback_cloud_run.sh` if rollback is required

## Recommended Runtime Settings

Interactive beta target:

```bash
ORTY_DEPLOYMENT_PROFILE=cloud_run_interactive
LLM_PROVIDER=vertex_ai
ENABLE_CLOUD_FALLBACK=false
ENABLE_PARALLEL_PROVIDER_RACE=false
ALLOW_LEGACY_CLIENT_HEADERS=false
```

Suggested service tuning:

- region: `us-central1`
- timeout: `60s`
- concurrency: `8`
- cpu: `1`
- memory: `1Gi`
- min instances: `0` for staging, `1` if cold starts are hurting the beta path

## Rollout Order

1. Apply the PostgreSQL schema to the target database with `python3 scripts/apply_postgres_schema.py`.
2. Run `bash scripts/deploy_cloud_run_phase1.sh` with the required Secret Manager settings.
3. Run `bash scripts/smoke_cloud_run_beta.sh` against the deployed URL.
4. Point Alfred staging to the Cloud Run URL and validate real-device latency.
5. If anything looks wrong, run `bash scripts/rollback_cloud_run.sh` with the previous ready revision.
6. Only then treat the Cloud Run path as the canonical beta backend.

## Rollback

The deploy script prints the previous ready revision if one exists. Roll back traffic with:

```bash
bash scripts/rollback_cloud_run.sh
```

Required environment variables: `PROJECT_ID`, `REGION`, `SERVICE_NAME`, and `TARGET_REVISION`.


For the current beta stage, keep one Cloud Run instance warm by default (MIN_INSTANCES=1) to reduce first-request auth and voice cold-start flakiness.
