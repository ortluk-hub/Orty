from typing import Literal

from pydantic import BaseModel, Field


class EscalationMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class EscalationContext(BaseModel):
    context_version: str | None = Field(default=None, max_length=100)
    summary_id: str | None = Field(default=None, max_length=100)
    local_summary: str | None = Field(default=None, max_length=4000)
    recent_messages: list[EscalationMessage] = Field(default_factory=list)
    memory_record_ids: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    history_limit: int = Field(default=10, ge=1, le=50)
    reset_conversation: bool = False
    persist: bool = True
    escalation_context: EscalationContext | None = None


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str
    used_history: int = 0
    handled_by: str | None = None
    provider: str | None = None
    fallback_used: bool = False
    context_version: str | None = None
    summary_id: str | None = None


class ClientCreateRequest(BaseModel):
    name: str | None = None
    preferences: dict = Field(default_factory=dict)


class ClientCreateResponse(BaseModel):
    client_id: str
    client_token: str
    name: str | None = None
    preferences: dict = Field(default_factory=dict)
    is_primary: bool = False
    created_at: str


class ClientSummaryResponse(BaseModel):
    client_id: str
    name: str | None = None
    preferences: dict = Field(default_factory=dict)
    is_primary: bool = False
    created_at: str
    last_seen_at: str | None = None


class ClientPreferencesUpdateRequest(BaseModel):
    preferences: dict = Field(default_factory=dict)


class ClientTokenRequest(BaseModel):
    client_id: str
    client_token: str


class ClientTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    expires_at: str
    client_id: str


class ClientRotateRequest(BaseModel):
    client_id: str
    client_token: str
    revoke_access_tokens: bool = True


class ClientRotateResponse(BaseModel):
    client_id: str
    client_token: str
    rotated_at: str


class ClientRevokeRequest(BaseModel):
    access_token: str | None = None


class ClientRevokeResponse(BaseModel):
    revoked: bool


class ClientMeResponse(BaseModel):
    client_id: str
    name: str | None = None
    preferences: dict = Field(default_factory=dict)
    is_primary: bool = False
    created_at: str
    last_seen_at: str | None = None
    auth_method: str
    is_admin: bool = False


class ClientIntrospectRequest(BaseModel):
    access_token: str


class ClientIntrospectResponse(BaseModel):
    found: bool
    active: bool
    client_id: str | None = None
    created_at: str | None = None
    expires_at: str | None = None
    revoked_at: str | None = None
    last_used_at: str | None = None


class MemoryRecordCreateRequest(BaseModel):
    client_id: str | None = None
    memory_type: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=20000)
    summary: str | None = Field(default=None, max_length=1000)
    tags: list[str] = Field(default_factory=list)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str | None = Field(default=None, max_length=200)
    external_key: str | None = Field(default=None, min_length=1, max_length=255)
    is_pinned: bool = False
    expires_at: int | None = None


class MemoryRecordResponse(BaseModel):
    record_id: str
    client_id: str
    memory_type: str
    content: str
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    importance: float
    source: str | None = None
    external_key: str | None = None
    is_pinned: bool = False
    expires_at: int | None = None
    created_at: str
    updated_at: str
    deleted_at: str | None = None


class MemoryRecordUpdateRequest(BaseModel):
    memory_type: str | None = Field(default=None, min_length=1, max_length=100)
    content: str | None = Field(default=None, min_length=1, max_length=20000)
    summary: str | None = Field(default=None, max_length=1000)
    tags: list[str] | None = Field(default=None)
    importance: float | None = Field(default=None, ge=0.0, le=1.0)
    source: str | None = Field(default=None, max_length=200)
    external_key: str | None = Field(default=None, min_length=1, max_length=255)
    is_pinned: bool | None = None
    expires_at: int | None = None


class MemorySyncItem(BaseModel):
    key: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=1000)
    sourceText: str = Field(min_length=1, max_length=20000)
    createdAt: int
    updatedAt: int
    isPinned: bool = False
    expiresAt: int | None = None


class MemorySyncRequest(BaseModel):
    client: str | None = Field(default=None, min_length=1, max_length=100)
    client_id: str | None = Field(default=None, min_length=1, max_length=255)
    memories: list[MemorySyncItem] = Field(default_factory=list)


class MemorySyncResponse(BaseModel):
    status: str
    syncedCount: int
    memories: list[MemorySyncItem] = Field(default_factory=list)


class MemorySummaryCreateRequest(BaseModel):
    client_id: str | None = None
    conversation_id: str = Field(min_length=1, max_length=120)
    context_version: str | None = Field(default=None, max_length=100)
    summary: str = Field(min_length=1, max_length=20000)
    source: str | None = Field(default=None, max_length=200)


class MemorySummaryResponse(BaseModel):
    summary_id: str
    client_id: str
    conversation_id: str
    context_version: str | None = None
    summary: str
    source: str | None = None
    created_at: str
    updated_at: str


class BotCreateRequest(BaseModel):
    bot_type: str
    config: dict = Field(default_factory=dict)
    owner_client_id: str | None = None


class BotCreateResponse(BaseModel):
    bot_id: str
    owner_client_id: str
    bot_type: str
    config: dict
    status: str
    created_at: str
    updated_at: str


class BotStatusResponse(BotCreateResponse):
    pass


class BotEventResponse(BaseModel):
    event_id: str
    bot_id: str
    owner_client_id: str
    event_type: str
    message: str | None = None
    created_at: str
    payload: dict = Field(default_factory=dict)
