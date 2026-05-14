-- Orty PostgreSQL schema v1, Phase 1.
--
-- This schema is intentionally beta-safe:
-- - preserves current operational table names where that reduces repository churn
-- - upgrades SQLite-only types to PostgreSQL-native types
-- - adds richer contextual-memory tables needed for stocks and other changing domains
-- - defers conversation normalization and embeddings until after durability cutover

BEGIN;

CREATE TABLE IF NOT EXISTS clients (
    client_id TEXT PRIMARY KEY,
    name TEXT,
    token_hash TEXT NOT NULL,
    preferences_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    access_tier TEXT NOT NULL DEFAULT 'free',
    lifecycle_status TEXT NOT NULL DEFAULT 'active',
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ
);

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS access_tier TEXT NOT NULL DEFAULT 'free';

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS lifecycle_status TEXT NOT NULL DEFAULT 'active';

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS uq_clients_primary_true
ON clients (is_primary)
WHERE is_primary = TRUE;

CREATE TABLE IF NOT EXISTS client_promotion_requests (
    request_id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    reviewer_client_id TEXT REFERENCES clients(client_id) ON DELETE SET NULL,
    rejection_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at TIMESTAMPTZ,
    CHECK (status IN ('pending', 'approved', 'rejected'))
);

CREATE INDEX IF NOT EXISTS idx_client_promotion_requests_status
ON client_promotion_requests (status);

CREATE INDEX IF NOT EXISTS idx_client_promotion_requests_client_id
ON client_promotion_requests (client_id);

CREATE TABLE IF NOT EXISTS client_access_tokens (
    token_hash TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_client_access_tokens_client_id
ON client_access_tokens (client_id);

CREATE INDEX IF NOT EXISTS idx_client_access_tokens_expires_at
ON client_access_tokens (expires_at);

CREATE TABLE IF NOT EXISTS model_settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id TEXT REFERENCES clients(client_id) ON DELETE SET NULL,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (role IN ('system', 'user', 'assistant', 'tool'))
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id_id
ON messages (conversation_id, id DESC);

CREATE INDEX IF NOT EXISTS idx_messages_client_conversation_id_id
ON messages (client_id, conversation_id, id DESC);

CREATE TABLE IF NOT EXISTS memory_entities (
    entity_id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    display_name TEXT,
    external_key TEXT,
    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status IN ('active', 'archived', 'deleted'))
);

CREATE INDEX IF NOT EXISTS idx_memory_entities_client_type_name
ON memory_entities (client_id, entity_type, canonical_name);

CREATE UNIQUE INDEX IF NOT EXISTS uq_memory_entities_client_type_external_key
ON memory_entities (client_id, entity_type, external_key)
WHERE external_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_memory_entities_aliases_gin
ON memory_entities
USING GIN (aliases);

CREATE INDEX IF NOT EXISTS idx_memory_entities_attributes_gin
ON memory_entities
USING GIN (attributes);

CREATE TABLE IF NOT EXISTS memory_records (
    record_id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    entity_id TEXT REFERENCES memory_entities(entity_id) ON DELETE SET NULL,
    memory_type TEXT NOT NULL,
    scope_kind TEXT NOT NULL DEFAULT 'client',
    scope_ref TEXT,
    content TEXT NOT NULL,
    summary TEXT,
    tags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    facets JSONB NOT NULL DEFAULT '{}'::jsonb,
    importance REAL NOT NULL DEFAULT 0.5,
    confidence REAL NOT NULL DEFAULT 0.7,
    source TEXT,
    source_ref TEXT,
    external_key TEXT,
    is_pinned BOOLEAN NOT NULL DEFAULT FALSE,
    freshness TEXT NOT NULL DEFAULT 'durable',
    valid_from TIMESTAMPTZ,
    expires_at BIGINT,
    last_observed_at TIMESTAMPTZ,
    source_created_at BIGINT,
    source_updated_at BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CHECK (importance >= 0.0 AND importance <= 1.0),
    CHECK (confidence >= 0.0 AND confidence <= 1.0),
    CHECK (scope_kind IN ('client', 'project', 'workspace', 'conversation', 'task', 'entity', 'global')),
    CHECK (freshness IN ('durable', 'refreshable', 'volatile', 'event'))
);

CREATE INDEX IF NOT EXISTS idx_memory_records_client_created
ON memory_records (client_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_records_client_type_created
ON memory_records (client_id, memory_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_records_client_scope_updated
ON memory_records (client_id, scope_kind, scope_ref, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_records_entity_updated
ON memory_records (entity_id, updated_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_memory_records_active_external_key
ON memory_records (client_id, external_key)
WHERE deleted_at IS NULL AND external_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_memory_records_tags_gin
ON memory_records
USING GIN (tags_json);

CREATE INDEX IF NOT EXISTS idx_memory_records_facets_gin
ON memory_records
USING GIN (facets);

CREATE TABLE IF NOT EXISTS memory_observations (
    observation_id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    entity_id TEXT NOT NULL REFERENCES memory_entities(entity_id) ON DELETE CASCADE,
    record_id TEXT REFERENCES memory_records(record_id) ON DELETE SET NULL,
    observation_type TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    valid_until TIMESTAMPTZ,
    value_number DOUBLE PRECISION,
    value_text TEXT,
    value_bool BOOLEAN,
    value_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    unit TEXT,
    source TEXT NOT NULL,
    source_ref TEXT,
    confidence REAL NOT NULL DEFAULT 0.7,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

CREATE INDEX IF NOT EXISTS idx_memory_observations_entity_type_observed
ON memory_observations (entity_id, observation_type, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_observations_client_type_observed
ON memory_observations (client_id, observation_type, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_observations_record_observed
ON memory_observations (record_id, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_observations_value_json_gin
ON memory_observations
USING GIN (value_json);

CREATE TABLE IF NOT EXISTS memory_entity_state (
    entity_id TEXT NOT NULL REFERENCES memory_entities(entity_id) ON DELETE CASCADE,
    state_key TEXT NOT NULL,
    value_number DOUBLE PRECISION,
    value_text TEXT,
    value_bool BOOLEAN,
    value_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    unit TEXT,
    as_of TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL,
    source_ref TEXT,
    confidence REAL NOT NULL DEFAULT 0.7,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (entity_id, state_key),
    CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

CREATE INDEX IF NOT EXISTS idx_memory_entity_state_as_of
ON memory_entity_state (as_of DESC);

CREATE TABLE IF NOT EXISTS memory_summaries (
    summary_id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    conversation_id TEXT,
    scope_kind TEXT NOT NULL DEFAULT 'conversation',
    scope_ref TEXT,
    context_version TEXT,
    summary TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    source TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (scope_kind IN ('conversation', 'entity', 'project', 'task', 'market', 'handoff', 'client'))
);

CREATE INDEX IF NOT EXISTS idx_memory_summaries_client_conversation_created
ON memory_summaries (client_id, conversation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_summaries_client_scope_created
ON memory_summaries (client_id, scope_kind, scope_ref, created_at DESC);

CREATE TABLE IF NOT EXISTS bug_reports (
    report_id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    client TEXT,
    source TEXT,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    details TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_created_at BIGINT,
    status TEXT NOT NULL DEFAULT 'pending',
    codey_task_id TEXT,
    codey_status TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_bug_reports_client_created
ON bug_reports (client_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_bug_reports_client_source_created
ON bug_reports (client_id, source, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_bug_reports_status_created
ON bug_reports (status, created_at DESC);

CREATE TABLE IF NOT EXISTS bots (
    bot_id TEXT PRIMARY KEY,
    owner_client_id TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    bot_type TEXT NOT NULL,
    config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_bots_owner_client_id
ON bots (owner_client_id);

CREATE TABLE IF NOT EXISTS bot_events (
    event_id TEXT PRIMARY KEY,
    bot_id TEXT NOT NULL REFERENCES bots(bot_id) ON DELETE CASCADE,
    owner_client_id TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_bot_events_bot_id_created_at
ON bot_events (bot_id, created_at DESC);

COMMIT;
