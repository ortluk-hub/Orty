# Alfred-Orty Integration Contract v1

Last updated: 2026-03-12
Status: Partially implemented, still evolving

## 1. Purpose

Define how Alfred (device assistant) and Orty (server assistant orchestration layer) interact now and going forward.

## 2. Roles and Responsibility

- Alfred:
  - User-facing assistant on each device.
  - Runs local-first inference for latency-sensitive and small/medium requests.
  - Decides when to escalate to Orty using `/chat`.
  - Manages its own device/client credentials and token lifecycle.
- Orty:
  - Assistant's assistant (coordination, memory, tools, orchestration).
  - Handles escalated requests from Alfred.
  - Chooses local server LLM vs cloud LLM fallback when available.
  - Owns centralized memory, policy, and multi-client isolation.

## 3. Identity and Authentication Model

Identity is per Alfred instance (client instance), not per end user.

Current auth endpoints:

- `POST /v1/clients/register`: public Alfred client registration using `ORTY_ALFRED_CLIENT_KEY`.
- `POST /v1/clients` (admin secret required): provision client identity.
- `POST /v1/auth/token`: exchange `client_id + client_token` for bearer access token.
- `POST /v1/auth/rotate`: rotate long-lived client credential.
- `POST /v1/auth/revoke`: revoke bearer token.
- `GET /v1/auth/me`: return current auth/client context.
- `POST /v1/auth/introspect` (admin only): inspect token state.

Compatibility note:

- Legacy `x-orty-client-id` + `x-orty-client-token` headers are still supported while `ALLOW_LEGACY_CLIENT_HEADERS=true`.
- Target end state: disable legacy headers and use bearer-only client auth.

## 4. Request Escalation Contract (`/chat`)

`/chat` is Alfred's escalation path when a request is too expensive or too slow for Alfred local models.

Target decision chain:

1. Alfred local LLM attempt (fast path).
2. Alfred escalates to Orty `/chat`.
3. Orty chooses:
   - Orty local server LLM when feasible.
   - Cloud LLM only for tasks that are too large for both Alfred and Orty local capacity in reasonable time.

Cloud usage policy:

- Reserve cloud for high-cost, high-complexity workloads only.
- Keep default path local-first to control cost/privacy/latency.

## 5. Memory Contract

### 5.1 Current state

- Conversation memory exists server-side and is scoped by `client_id + conversation_id`.
- `/chat` supports conversation continuity and bounded history retrieval.
- Explicit long-term memory APIs are implemented:
  - `POST /v1/memory/records`
  - `GET /v1/memory/records`
  - `GET /v1/memory/records/{record_id}`
  - `PATCH /v1/memory/records/{record_id}`
  - `DELETE /v1/memory/records/{record_id}`
  - `POST /v1/memory/summaries`
  - `GET /v1/memory/summaries`
- Alfred snapshot sync is implemented through:
  - `POST /memory/sync` (compatibility route)
  - `POST /v1/memory/sync` (versioned route)
- Sync writes are canonicalized into `memory_records` rows using `external_key`, and records missing from a later sync snapshot are soft-deleted only within the sync-managed subset.

### 5.2 Current Alfred sync payload

Current sync request shape:

- `client` or `client_id` (optional override; admin only if targeting another client)
- `memories[]`
  - `key`
  - `category`
  - `summary`
  - `sourceText`
  - `createdAt`
  - `updatedAt`
  - `isPinned`
  - `expiresAt`

Current sync response shape:

- `status`
- `syncedCount`
- `memories[]` in canonical server form

### 5.3 Remaining future state

Further Alfred work still needed:

- richer query/relevance semantics beyond CRUD + snapshot sync
- explicit retention and expiration policies
- production-facing rollout decisions for disabling legacy auth headers

Minimum record fields:

- `record_id`, `client_id`, `memory_type`, `content`, `summary`, `tags`, `importance`, `source`, `created_at`, `updated_at`.

Security and isolation requirements:

- Clients can only access their own memory unless admin.
- Full auditability for writes/updates/deletes.

## 6. Reliability and Operational Expectations

- Alfred handles token renewal before expiry.
- Alfred retries transient `5xx` and network errors with bounded backoff.
- Orty should provide structured error payloads and clear status codes (`401`, `403`, `429`, `5xx`).
- Rotation should invalidate old credentials; revocation should invalidate active access tokens quickly.

## 7. Rollout Sequence

1. Use bearer tokens for Alfred integration (`/v1/auth/token`).
2. Alfred adopts `/v1/auth/me` health/identity check on startup.
3. Use `/memory/sync` or `/v1/memory/sync` for Alfred snapshot memory sync.
4. Expand Alfred use of `/v1/memory/*` for explicit long-term memory operations beyond snapshot sync.
5. Turn off legacy header auth (`ALLOW_LEGACY_CLIENT_HEADERS=false`).
6. Introduce optional cloud fallback policy controls (per-client policy and quotas).

## 8. Non-Goals

- No human user login in Orty for Alfred runtime path.
- No requirement for `/ui` to represent Alfred auth behavior.
