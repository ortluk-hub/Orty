from typing import Any, Literal

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


class ChatToolCall(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    arguments: Any = Field(default_factory=dict)


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    history_limit: int = Field(default=10, ge=1, le=50)
    reset_conversation: bool = False
    persist: bool = True
    client: str | None = Field(default=None, min_length=1, max_length=120)
    assistant_name: str | None = Field(default=None, min_length=1, max_length=120)
    personality_preset: str | None = Field(default=None, min_length=1, max_length=80)
    system_prompt: str | None = Field(default=None, max_length=12000)
    recent_messages: list[EscalationMessage] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    tool_choice: Any | None = None
    escalation_context: EscalationContext | None = None


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str
    used_history: int = 0
    tool_calls: list[ChatToolCall] = Field(default_factory=list)
    handled_by: str | None = None
    provider: str | None = None
    fallback_used: bool = False
    context_version: str | None = None
    summary_id: str | None = None


class SpeechRecognizeRequest(BaseModel):
    audio_base64: str = Field(min_length=1)
    language_code: str = Field(default="en-US", min_length=2, max_length=32)
    api_key: str | None = Field(default=None, min_length=1, max_length=512)


class SpeechRecognizeResponse(BaseModel):
    transcript: str | None = None
    no_speech: bool = False
    provider: str = "google_speech_v1"


class SpeechSynthesizeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    language_code: str = Field(default="en-US", min_length=2, max_length=32)
    api_key: str | None = Field(default=None, min_length=1, max_length=512)
    voice_name: str | None = Field(default=None, min_length=1, max_length=128)
    speaking_rate: float = Field(default=1.0, ge=0.25, le=2.0)
    pitch: float = Field(default=0.0, ge=-20.0, le=20.0)
    audio_encoding: str = Field(default="MP3", min_length=3, max_length=32)


class SpeechSynthesizeResponse(BaseModel):
    audio_base64: str = Field(min_length=1)
    audio_encoding: str = "MP3"
    provider: str = "google_tts_v1"


class ClientCreateRequest(BaseModel):
    name: str | None = None
    preferences: dict = Field(default_factory=dict)


class ClientRegisterRequest(BaseModel):
    client_key: str = Field(min_length=1, max_length=200)
    name: str | None = None
    preferences: dict = Field(default_factory=dict)


class ClientCreateResponse(BaseModel):
    client_id: str
    client_token: str
    name: str | None = None
    preferences: dict = Field(default_factory=dict)
    is_primary: bool = False
    access_tier: Literal["free", "premium", "dedicated", "enterprise"] = "free"
    lifecycle_status: Literal["active", "stale", "revoked"] = "active"
    revoked_at: str | None = None
    created_at: str


class ClientSummaryResponse(BaseModel):
    client_id: str
    name: str | None = None
    preferences: dict = Field(default_factory=dict)
    is_primary: bool = False
    is_admin: bool = False
    access_tier: Literal["free", "premium", "dedicated", "enterprise"] = "free"
    lifecycle_status: Literal["active", "stale", "revoked"] = "active"
    revoked_at: str | None = None
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


class ClientPromotionRequest(BaseModel):
    reason: str = Field(
        min_length=10,
        max_length=2000,
        description="Reason for requesting admin status",
    )
    admin_secret_hash: str = Field(
        min_length=1,
        max_length=100,
        description="Hash of admin secret",
    )


class ClientPromotionRequestResponse(BaseModel):
    request_id: str
    client_id: str
    reason: str
    status: str
    created_at: str


class ClientPromotionApproveRequest(BaseModel):
    request_id: str


class ClientPromotionRejectRequest(BaseModel):
    request_id: str
    reason: str = Field(
        min_length=1,
        max_length=1000,
        description="Reason for rejection",
    )


class ClientPromotionListResponse(BaseModel):
    requests: list[dict]
    total: int


class ClientMeResponse(BaseModel):
    client_id: str
    name: str | None = None
    preferences: dict = Field(default_factory=dict)
    is_primary: bool = False
    access_tier: Literal["free", "premium", "dedicated", "enterprise"] = "free"
    lifecycle_status: Literal["active", "stale", "revoked"] = "active"
    revoked_at: str | None = None
    created_at: str
    last_seen_at: str | None = None
    auth_method: str
    is_admin: bool = False


class ClientAccessTierUpdateRequest(BaseModel):
    access_tier: Literal["free", "premium", "dedicated", "enterprise"]


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


class ModelRegistryItemResponse(BaseModel):
    id: str
    name: str
    size_bytes: int
    sha256: str
    is_default: bool = False


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


class BugReportCreateRequest(BaseModel):
    client: str | None = Field(default=None, min_length=1, max_length=100)
    client_id: str | None = Field(default=None, min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=2000)
    details: str = Field(min_length=1, max_length=40000)
    metadata: dict[str, str] = Field(default_factory=dict)
    createdAt: int


class BugReportCreateResponse(BaseModel):
    status: str
    report_id: str


class BugReportRecordResponse(BaseModel):
    report_id: str
    client_id: str
    client: str | None = None
    source: str | None = None
    title: str
    summary: str
    details: str
    metadata: dict[str, str] = Field(default_factory=dict)
    createdAt: int
    created_at: str
    updated_at: str


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
