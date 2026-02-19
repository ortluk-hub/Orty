from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    history_limit: int = Field(default=10, ge=1, le=50)
    reset_conversation: bool = False
    persist: bool = True


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str
    used_history: int = 0


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
