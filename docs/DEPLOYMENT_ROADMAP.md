# Orty Deployment Roadmap

This document is the short operational roadmap for getting Orty from an active alpha repo to a clean beta deployment lane.

It is intentionally simple: one marker per deployment milestone, each with a clear exit condition.

## Current Marker

D1 in progress

Orty has the right broad shape for deployment, but the repo and deployment story still need cleanup before the first clean beta artifact push.

## Markers

### D0 Repo Cleanup And Deployment Alignment

Goal:
- make the repo tell one consistent deployment story
- remove obvious repo noise from the deployment path
- define the artifact and release lane clearly

Exit criteria:
- README status and Cloud Run docs agree on current reality
- deployment artifact is explicitly described as a container image
- deployment roadmap markers exist and are linked from the README
- backup-file noise is excluded from the repo

### D1 PostgreSQL-Backed Cloud Run Beta Cutover

Goal:
- make Cloud Run durable enough for beta use

Exit criteria:
- DATABASE_URL is the production persistence path
- PostgreSQL schema is applied and validated
- Cloud Run deploy flow injects database config cleanly
- interactive beta smoke checks pass against the deployed service

Smoke checks:
- GET /health
- POST /chat
- POST /v1/auth/token
- GET /v1/auth/me
- POST /v1/memory/sync
- POST /v1/stt/recognize
- POST /v1/tts/synthesize

### D2 Artifact-First Beta Release Discipline

Goal:
- ensure production deployments come from an intentional release lane

Exit criteria:
- release builds come from the official repo lineage on orty-server
- production deploys consume a tagged container image, not a working tree
- release notes or changelog entries identify deployment-relevant changes
- a repeatable verification pass exists before deploy

## Immediate Next Steps

1. Apply the PostgreSQL schema to the target database from the official repo lane.
2. Deploy the Cloud Run service with Vertex AI as the primary provider and no local inference dependency.
3. Run the scripted smoke suite against the deployed service.
4. Treat the first tagged container image and successful smoke run as the entry point into D2.
