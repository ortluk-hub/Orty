# Orty PostgreSQL Migration Phase 1

This document turns the v1 memory schema into the first concrete migration slice.

The goal of Phase 1 is not to finish every future memory feature. The goal is to:

- get Orty off SQLite so Cloud Run can become durable
- preserve today's auth, chat, memory, and bug-report behavior
- leave room for richer contextual memory without forcing a broad rewrite before beta
- support stock and other time-varying domains with a native current-state pattern instead of repeated recomputation

## Phase 1 Outcome

When this slice is complete, Orty should be able to:

- boot against PostgreSQL using `DATABASE_URL`
- persist all current SQLite-backed product data durably
- keep Alfred-compatible message and memory sync working
- expose a schema that already supports entity memory, observations, and latest-known state
- stage and cut over to Cloud Run without pretending SQLite-on-ephemeral-disk is durable

This phase does **not** need to finish:

- Codey migration
- semantic embedding retrieval
- bot-worker durability redesign
- conversation normalization beyond the current `conversation_id` string flow

## Design Choice For Beta Safety

The high-level schema proposal introduced `memory_items` as the canonical durable-memory table.

For Phase 1, the safest migration is to keep the operational table name `memory_records` and upgrade its shape instead of renaming the table during the same slice. That keeps repository churn low while still giving Orty a better memory foundation immediately.

So the concrete Phase 1 memory shape is:

- keep `messages`
- keep `memory_records`
- keep `memory_summaries`
- add `memory_entities`
- add `memory_observations`
- add `memory_entity_state`

This means:

- current Alfred memory sync can keep mapping into `memory_records`
- richer domains can start using entity-linked memory without a second storage migration
- stock state can be stored directly instead of re-derived from old chat turns

## Canonical Table Set For Phase 1

Phase 1 PostgreSQL should define these tables as canonical:

1. `clients`
2. `client_access_tokens`
3. `client_promotion_requests`
4. `messages`
5. `memory_entities`
6. `memory_records`
7. `memory_observations`
8. `memory_entity_state`
9. `memory_summaries`
10. `bug_reports`
11. `bots`
12. `bot_events`

## SQLite To PostgreSQL Mapping

### `clients`

SQLite:

- `preferences_json TEXT`
- `is_primary INTEGER`
- `is_admin INTEGER`
- timestamps stored as ISO `TEXT`

PostgreSQL:

- `preferences JSONB`
- `is_primary BOOLEAN`
- `is_admin BOOLEAN`
- `created_at TIMESTAMPTZ`
- `last_seen_at TIMESTAMPTZ`

Notes:

- keep `client_id` as `TEXT` in Phase 1 so existing client ids and auth paths migrate without coercion work
- keep the partial unique primary-client constraint

### `client_access_tokens`

SQLite:

- all timestamps stored as ISO `TEXT`

PostgreSQL:

- `created_at TIMESTAMPTZ`
- `expires_at TIMESTAMPTZ`
- `revoked_at TIMESTAMPTZ`
- `last_used_at TIMESTAMPTZ`

Notes:

- keep `token_hash` as primary key

### `client_promotion_requests`

SQLite:

- plain text status flow
- timestamps stored as ISO `TEXT`

PostgreSQL:

- same logical shape
- timestamps promoted to `TIMESTAMPTZ`

Notes:

- the current `json_set()` write in promotion approval moves out of SQL and into repository-side JSON merge logic

### `messages`

SQLite:

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `conversation_id TEXT`
- `created_at DATETIME DEFAULT CURRENT_TIMESTAMP`

PostgreSQL:

- `id BIGINT GENERATED ALWAYS AS IDENTITY`
- `conversation_id TEXT`
- `created_at TIMESTAMPTZ DEFAULT now()`
- optional `metadata JSONB DEFAULT '{}'`

Notes:

- keep `conversation_id` as plain `TEXT` in Phase 1
- defer a separate `conversations` table until after the durability cutover

### `memory_records`

SQLite:

- one flat durable-memory table
- `tags_json TEXT`
- integer booleans
- `expires_at`, `source_created_at`, `source_updated_at` stored as integer epoch milliseconds
- partial unique index on active `(client_id, external_key)`

PostgreSQL:

- keep the table name `memory_records`
- change `tags_json` to `tags JSONB`
- add `facets JSONB`
- add `entity_id TEXT NULL REFERENCES memory_entities(entity_id)`
- add `scope_kind TEXT DEFAULT 'client'`
- add `scope_ref TEXT`
- add `confidence REAL DEFAULT 0.7`
- add `freshness TEXT DEFAULT 'durable'`
- add `valid_from TIMESTAMPTZ`
- convert `expires_at`, `source_created_at`, `source_updated_at` to `TIMESTAMPTZ`
- keep `deleted_at` soft-delete model
- keep partial unique index on active `(client_id, external_key)`

Notes:

- this is the key compromise that keeps beta migration practical while still making memory deeper than raw chat history
- current Alfred sync continues to write here
- future entity-aware memory can link records to `memory_entities`

### `memory_entities`

New in PostgreSQL Phase 1.

Purpose:

- anchor durable knowledge to a real entity
- support stocks, places, devices, repos, people, and projects cleanly

Key columns:

- `entity_id TEXT PRIMARY KEY`
- `entity_type TEXT`
- `canonical_name TEXT`
- `external_key TEXT`
- `aliases JSONB`
- `attributes JSONB`

### `memory_observations`

New in PostgreSQL Phase 1.

Purpose:

- represent time-varying facts without flattening them into durable records

Examples:

- stock price snapshots
- earnings dates
- target prices
- device state observations
- status checkpoints

### `memory_entity_state`

New in PostgreSQL Phase 1.

Purpose:

- cache the latest known state for an entity so Orty can answer from current remembered state instead of aggregating old observations every turn

Examples:

- `last_price`
- `day_change_pct`
- `average_cost`
- `position_size`
- `earnings_date`
- `preferred_tts_voice`

### `memory_summaries`

SQLite:

- conversation-focused summary table

PostgreSQL:

- keep current fields
- add `scope_kind`, `scope_ref`, and `metadata JSONB`

Notes:

- current usage can continue to be conversation-centric
- the schema no longer blocks project, market, or handoff summaries later

### `bug_reports`

SQLite:

- `metadata_json TEXT`
- live DB drift already includes `status`, `codey_task_id`, `codey_status`

PostgreSQL:

- `metadata JSONB`
- explicitly define `status`, `codey_task_id`, `codey_status`
- timestamps as `TIMESTAMPTZ`

Notes:

- treat the live schema as canonical, not the old initializer drift

### `bots` and `bot_events`

SQLite:

- `config_json TEXT`
- `payload_json TEXT`

PostgreSQL:

- `config JSONB`
- `payload JSONB`
- timestamps as `TIMESTAMPTZ`

Notes:

- these stay in schema for completeness
- Cloud Run interactive still keeps the bot control surface disabled in the current deployment profile

## Default Representation For Stock Memory

Phase 1 should support stock memory as a first-class pattern immediately.

### Entity

Use `memory_entities` for the instrument:

- `entity_type = 'instrument'`
- `external_key = 'ticker:NASDAQ:AAPL'`
- `attributes = { "ticker": "AAPL", "exchange": "NASDAQ", "asset_class": "equity", "currency": "USD" }`

### Durable Context

Use `memory_records` for durable context:

- `memory_type = 'market_thesis'`
- `memory_type = 'watch_rule'`
- `memory_type = 'constraint'`
- `memory_type = 'preference'`

Examples:

- user wants alerts below a certain price
- user prefers dividend growers over speculative biotech
- thesis about why the instrument matters

### Time-Varying Facts

Use `memory_observations` for changing values:

- `price_snapshot`
- `earnings_date`
- `dividend_date`
- `position_snapshot`
- `target_price`
- `risk_event`

### Current Known State

Use `memory_entity_state` for fast recall:

- `last_price`
- `day_change_pct`
- `position_size`
- `average_cost`
- `earnings_date`
- `thesis_status`

This is the pattern that avoids recomputation from raw history on every turn.

## Minimal Repository Adapter Plan

Phase 1 should introduce a thin database abstraction, not a broad ORM rewrite.

### New Components

- `service/storage/database.py`
  - `Database` protocol / base class
  - `DatabaseConnection` wrapper with `execute`, `fetchone`, `fetchall`
- `service/storage/sqlite_db.py`
  - current SQLite implementation moved here with minimal change
- `service/storage/postgres_db.py`
  - PostgreSQL implementation using `psycopg`

### Config Changes

- add `DATABASE_URL`
- if `DATABASE_URL` is set, boot PostgreSQL
- otherwise keep current SQLite path for local/dev fallback until cutover is complete

### Query Strategy

Do **not** introduce SQLAlchemy in this slice.

Use named parameters in repository SQL and let the adapter normalize them per backend:

- repository SQL uses a single named-parameter convention
- SQLite adapter rewrites to SQLite parameter style
- PostgreSQL adapter passes through to `psycopg`

This avoids converting every repository twice.

### Repository Cutover Order

1. `ClientsRepository`
2. `BugReportsRepository`
3. `MemoryStore`
4. `MemoryRecordsRepository`
5. `MemorySummariesRepository`
6. `BotsRepository`
7. `BotEventsRepository`

Reason:

- auth and bug reports are low-shape-risk but operationally important
- message and memory durability matter most for the Cloud Run cutover
- bot tables are least urgent for the interactive hosted path

## Data Import Plan

Use a one-off importer script for the current SQLite file.

Suggested file:

- `scripts/import_sqlite_to_postgres.py`

Responsibilities:

1. read from the current SQLite DB path
2. insert into PostgreSQL in dependency order
3. preserve ids exactly
4. convert JSON text to `jsonb`
5. convert integer booleans to `boolean`
6. convert ISO timestamps to `TIMESTAMPTZ`
7. convert epoch-millisecond fields in `memory_records` to `TIMESTAMPTZ`
8. upsert safely on rerun where appropriate

Import order:

1. `clients`
2. `client_access_tokens`
3. `client_promotion_requests`
4. `messages`
5. `memory_entities` (initially empty unless seeded)
6. `memory_records`
7. `memory_observations`
8. `memory_entity_state`
9. `memory_summaries`
10. `bug_reports`
11. `bots`
12. `bot_events`

## Validation Checklist

Before Cloud Run staging:

1. client creation and token verification work against PostgreSQL
2. `/v1/auth/token` and `/v1/auth/me` pass
3. `/chat` persists messages
4. current Alfred memory sync still upserts durable memory correctly
5. bug reports round-trip with status fields intact
6. existing tests pass against PostgreSQL-backed runtime for touched repositories
7. importer can be run twice without duplicating active `external_key` memory rows

## Rollout Order That Minimizes Beta Risk

### Slice A

- land canonical PostgreSQL DDL
- land DB adapter skeleton
- no behavioral cutover yet

### Slice B

- port auth/client repos
- port bug report repo
- run focused tests

### Slice C

- port message/memory repos
- import existing SQLite data
- run focused tests

### Slice D

- stage Orty on Cloud Run with PostgreSQL
- keep bot control surface disabled
- smoke `/health`, `/v1/auth/*`, `/chat`, `/v1/tts`, `/v1/stt`

### Slice E

- start writing richer domain memory into `memory_entities`, `memory_observations`, and `memory_entity_state`
- stock support is one of the first intended consumers

## Bottom Line

Phase 1 should optimize for durable hosting now and richer memory shortly after, without forcing a destabilizing rename-and-rewrite cycle before beta.

That is why the concrete first move is:

- PostgreSQL now
- better memory shape now
- table-name churn later only if it still buys us something
