# Orty Postgres Memory Schema v1

This document defines the first durable PostgreSQL memory shape for Orty.

The goal is not just to preserve raw chat history. The goal is to support:

- conversational continuity
- canonical long-term memory
- structured contextual recall
- time-varying observations
- future semantic retrieval
- domain-specific patterns such as stock tracking without recomputing everything from raw history

## Design Goals

1. Keep chat history and memory separate.
2. Store canonical facts/preferences/context as first-class records.
3. Support entity-centric memory so people, projects, repos, instruments, and places can accumulate context cleanly.
4. Support time-series observations for data that changes over time.
5. Support a cached latest-known state for fast recall.
6. Keep Alfred-compatible sync straightforward.
7. Leave room for `pgvector` later without making it mandatory on day one.

## Core Principles

- `messages` are for thread continuity, not durable truth.
- `memory_items` are durable/contextual truths, preferences, constraints, summaries, and learned patterns.
- `memory_observations` are time-varying measurements or events.
- `memory_entity_state` is the latest-known snapshot cache so Orty does not need to re-derive current state from all prior observations.
- `memory_entities` are the anchors that tie contextual memory and observations together.

## Proposed Tables

### 1. `clients`

Keep the current client identity model, but move to PostgreSQL-native types.

Suggested columns:

- `client_id text primary key`
- `name text`
- `token_hash text not null`
- `preferences jsonb not null default '{}'::jsonb`
- `is_primary boolean not null default false`
- `is_admin boolean not null default false`
- `created_at timestamptz not null default now()`
- `last_seen_at timestamptz`

Indexes:

- unique partial index on `is_primary` where `is_primary = true`

### 2. `conversations`

Optional but recommended. This normalizes thread metadata instead of treating `conversation_id` as a naked string only inside messages.

Suggested columns:

- `conversation_id uuid primary key`
- `client_id text not null references clients(client_id)`
- `channel text not null default 'chat'`
- `title text`
- `created_at timestamptz not null default now()`
- `last_activity_at timestamptz not null default now()`
- `metadata jsonb not null default '{}'::jsonb`

Indexes:

- `(client_id, last_activity_at desc)`

### 3. `messages`

Raw turn history for thread continuity.

Suggested columns:

- `message_id bigint generated always as identity primary key`
- `conversation_id uuid not null references conversations(conversation_id)`
- `client_id text references clients(client_id)`
- `role text not null`
- `content text not null`
- `tool_name text`
- `metadata jsonb not null default '{}'::jsonb`
- `created_at timestamptz not null default now()`

Constraints:

- check `role in ('system', 'user', 'assistant', 'tool')`

Indexes:

- `(conversation_id, message_id desc)`
- `(client_id, conversation_id, message_id desc)`

### 4. `memory_entities`

Canonical anchors for things Orty knows about.

Examples:

- person
- place
- organization
- project
- repository
- device
- topic
- instrument
- watchlist

Suggested columns:

- `entity_id uuid primary key`
- `client_id text not null references clients(client_id)`
- `entity_type text not null`
- `canonical_name text not null`
- `display_name text`
- `external_key text`
- `aliases jsonb not null default '[]'::jsonb`
- `attributes jsonb not null default '{}'::jsonb`
- `status text not null default 'active'`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

Indexes:

- `(client_id, entity_type, canonical_name)`
- unique partial index on `(client_id, entity_type, external_key)` where `external_key is not null`
- GIN on `aliases`
- GIN on `attributes`

### 5. `memory_items`

Canonical long-term memories and contextual records.

This replaces the idea that all durable memory should be one flat bucket.

Suggested columns:

- `memory_item_id uuid primary key`
- `client_id text not null references clients(client_id)`
- `entity_id uuid references memory_entities(entity_id)`
- `scope_kind text not null`
- `scope_ref text`
- `memory_kind text not null`
- `title text`
- `content text not null`
- `summary text`
- `source text`
- `source_ref text`
- `external_key text`
- `tags jsonb not null default '[]'::jsonb`
- `facets jsonb not null default '{}'::jsonb`
- `importance real not null default 0.5`
- `confidence real not null default 0.7`
- `pinned boolean not null default false`
- `freshness text not null default 'durable'`
- `valid_from timestamptz`
- `valid_until timestamptz`
- `last_observed_at timestamptz`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`
- `deleted_at timestamptz`

Suggested `scope_kind` values:

- `client`
- `project`
- `workspace`
- `conversation`
- `task`
- `entity`
- `global`

Suggested `memory_kind` values:

- `preference`
- `profile_fact`
- `relationship`
- `constraint`
- `project_context`
- `workflow`
- `location_context`
- `market_thesis`
- `watch_rule`
- `summary_anchor`
- `habit`
- `standing_instruction`

Suggested `freshness` values:

- `durable`
- `refreshable`
- `volatile`
- `event`

Indexes:

- `(client_id, scope_kind, scope_ref, updated_at desc)`
- `(client_id, memory_kind, updated_at desc)`
- `(entity_id, updated_at desc)`
- unique partial index on `(client_id, external_key)` where `deleted_at is null and external_key is not null`
- GIN on `tags`
- GIN on `facets`

### 6. `memory_item_links`

Links related memories together without flattening everything into one blob.

Suggested columns:

- `from_item_id uuid not null references memory_items(memory_item_id)`
- `to_item_id uuid not null references memory_items(memory_item_id)`
- `link_type text not null`
- `weight real not null default 1.0`
- `source text`
- `created_at timestamptz not null default now()`

Primary key:

- `(from_item_id, to_item_id, link_type)`

Examples:

- `supports`
- `contradicts`
- `summarizes`
- `belongs_to_project`
- `about_entity`
- `supersedes`

### 7. `memory_observations`

Time-varying measurements and events.

This is the table that makes stock tracking, device state history, or repeated market notes easy to represent.

Suggested columns:

- `observation_id uuid primary key`
- `client_id text not null references clients(client_id)`
- `entity_id uuid not null references memory_entities(entity_id)`
- `memory_item_id uuid references memory_items(memory_item_id)`
- `observation_type text not null`
- `observed_at timestamptz not null`
- `valid_until timestamptz`
- `value_number double precision`
- `value_text text`
- `value_bool boolean`
- `value_json jsonb not null default '{}'::jsonb`
- `unit text`
- `source text not null`
- `source_ref text`
- `confidence real not null default 0.7`
- `created_at timestamptz not null default now()`

Indexes:

- `(entity_id, observation_type, observed_at desc)`
- `(client_id, observation_type, observed_at desc)`
- `(memory_item_id, observed_at desc)`
- GIN on `value_json`

### 8. `memory_entity_state`

Latest-known snapshot cache.

This is important for stock tracking and other high-change domains. It lets Orty answer fast with the current remembered state instead of aggregating every prior observation on each turn.

Suggested columns:

- `entity_id uuid not null references memory_entities(entity_id)`
- `state_key text not null`
- `value_number double precision`
- `value_text text`
- `value_bool boolean`
- `value_json jsonb not null default '{}'::jsonb`
- `unit text`
- `as_of timestamptz not null`
- `source text not null`
- `source_ref text`
- `confidence real not null default 0.7`
- `updated_at timestamptz not null default now()`

Primary key:

- `(entity_id, state_key)`

Examples of `state_key`:

- `last_price`
- `day_change_pct`
- `position_size`
- `average_cost`
- `earnings_date`
- `target_price`
- `thesis_status`
- `last_known_location`
- `preferred_tts_voice`

### 9. `memory_summaries`

Compressed summaries at different scopes.

Suggested columns:

- `summary_id uuid primary key`
- `client_id text not null references clients(client_id)`
- `conversation_id uuid references conversations(conversation_id)`
- `scope_kind text not null`
- `scope_ref text`
- `summary_kind text not null`
- `context_version text`
- `summary text not null`
- `metadata jsonb not null default '{}'::jsonb`
- `source text`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

Suggested `summary_kind` values:

- `conversation_rollup`
- `entity_rollup`
- `project_rollup`
- `market_rollup`
- `handoff_rollup`

Indexes:

- `(client_id, scope_kind, scope_ref, created_at desc)`
- `(conversation_id, created_at desc)`

### 10. `memory_embeddings` (Optional Day 2)

Add only when retrieval quality needs semantic search.

Suggested columns:

- `embedding_id uuid primary key`
- `owner_table text not null`
- `owner_id uuid not null`
- `embedding_model text not null`
- `embedding vector(768)`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

Indexes:

- vector index when `pgvector` is enabled
- `(owner_table, owner_id)`

## Default Stock Tracking Pattern

Stock and market memory should be a first-class pattern, not an accidental one.

Use this shape by default:

### `memory_entities`

Represent the instrument itself:

- `entity_type = 'instrument'`
- `canonical_name = 'Apple Inc.'`
- `external_key = 'ticker:NASDAQ:AAPL'`
- `attributes = { "ticker": "AAPL", "exchange": "NASDAQ", "asset_class": "equity", "currency": "USD" }`

### `memory_items`

Represent durable contextual knowledge:

- `memory_kind = 'market_thesis'`
- `memory_kind = 'watch_rule'`
- `memory_kind = 'preference'`
- `memory_kind = 'constraint'`

Examples:

- "User watches AAPL for AI-device exposure."
- "Alert if AAPL falls below 190."
- "User prefers dividend growers over high-beta momentum names."
- "Treat earnings-week commentary as volatile unless confirmed twice."

### `memory_observations`

Represent time-varying facts:

- `observation_type = 'price_snapshot'`
- `observation_type = 'earnings_date'`
- `observation_type = 'dividend_date'`
- `observation_type = 'position_snapshot'`
- `observation_type = 'target_price'`
- `observation_type = 'news_note'`
- `observation_type = 'risk_event'`

### `memory_entity_state`

Represent current remembered state:

- `last_price`
- `day_change_pct`
- `average_cost`
- `position_size`
- `earnings_date`
- `thesis_status`

This gives Orty:

- fast current-state answers from `memory_entity_state`
- time-series recall from `memory_observations`
- durable reasoning context from `memory_items`

That is exactly the pattern we want for finance-style memory: current state is stored directly, history remains available, and durable interpretation sits beside it.

## Alfred Compatibility Mapping

Current Alfred-compatible sync can map like this:

- current `messages` -> `messages`
- current `memory_records` -> `memory_items`
- current `memory_summaries` -> `memory_summaries`
- `external_key` remains the sync-safe id for canonical upserts

Suggested v1 compatibility mapping:

- `category`/`memory_type` from Alfred -> `memory_kind`
- Alfred sync `key` -> `external_key`
- Alfred sync `summary` -> `summary`
- Alfred sync `sourceText` -> `content`
- Alfred sync pinning -> `pinned`
- Alfred sync time bounds -> `valid_until` or `last_observed_at`

## Migration Deltas From Current SQLite

### Straightforward

- `TEXT` timestamps -> `timestamptz`
- integer booleans -> `boolean`
- `*_json TEXT` -> `jsonb`
- existing uuid-like ids stay application-generated

### Needs Attention

- replace `SQLiteDB` with a driver-agnostic database adapter
- convert raw `?` placeholders to PostgreSQL driver parameters
- replace SQLite `json_set()` usage in client promotion handling
- replace `rowid` dedupe logic with explicit SQL using canonical keys or a window-function cleanup query
- make the bug report schema canonical instead of relying on drift

## Canonical Bug Report Shape

The live SQLite database already contains these fields even though the base initializer drifted:

- `status`
- `codey_task_id`
- `codey_status`

Postgres v1 should define them explicitly from day one.

Suggested additions to `bug_reports`:

- `status text not null default 'pending'`
- `codey_task_id text`
- `codey_status text`

## Recommended Rollout Order

1. Introduce a neutral `Database` adapter and `DATABASE_URL`.
2. Land canonical PostgreSQL DDL and migration scripts.
3. Port repositories from SQLite-specific SQL to PostgreSQL-safe SQL.
4. Import SQLite data into PostgreSQL.
5. Move Orty Cloud Run staging to PostgreSQL.
6. Only after that, call the hosted Orty backend durable.

## Bottom Line

PostgreSQL is not just acceptable for deep contextual memory. It is a much better fit than SQLite for the memory shape Orty wants:

- chat continuity
- durable contextual facts
- structured entity memory
- time-varying observations
- fast latest-known state
- future semantic retrieval

And for stock tracking specifically, `memory_entities + memory_observations + memory_entity_state + memory_items` gives Orty a native pattern for remembered market context instead of repeatedly rebuilding it from raw chat.
