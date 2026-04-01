import base64
import hashlib
import hmac
from html import escape
from pathlib import Path
import time

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from service.ai import ChatRequestContext
from service.api.deps import ensure_primary_client, get_runtime
from service.config import settings
from service.models.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix='/ui', tags=['ui'], redirect_slashes=False)
root_router = APIRouter(tags=['ui'])
UI_SESSION_COOKIE = "orty_ui_session"
UI_SESSION_TTL_SECONDS = 60 * 60 * 12


def _candidate_alfred_roots() -> list[Path]:
    configured = settings.ALFRED_DOCS_ROOT
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).expanduser())

    service_root = Path(__file__).resolve().parents[3]
    cwd = Path.cwd()
    candidates.extend(
        [
            cwd / 'Alfred' / 'Alfred',
            cwd.parent / 'Alfred' / 'Alfred',
            service_root.parent / 'Alfred' / 'Alfred',
            Path('/home/ortluk/ortluk-hub/Alfred/Alfred'),
        ]
    )

    deduped: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        normalized = candidate.resolve(strict=False)
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _resolve_alfred_root() -> Path:
    for candidate in _candidate_alfred_roots():
        if candidate.exists():
            return candidate
    configured = settings.ALFRED_DOCS_ROOT
    if configured:
        return Path(configured).expanduser()
    return _candidate_alfred_roots()[0]


def _mission_docs() -> dict[str, tuple[str, Path]]:
    alfred_root = _resolve_alfred_root()
    return {
        'jane-charter': ('Jane Charter', alfred_root / 'JANE_CHARTER.md'),
        'voice-and-identity-contract': (
            'Voice And Identity Contract',
            alfred_root / 'VOICE_AND_IDENTITY_CONTRACT.md',
        ),
        'monetization-guardrails': (
            'Monetization Guardrails',
            alfred_root / 'MONETIZATION_GUARDRAILS.md',
        ),
    }


def _render_markdown_document(title: str, path: Path) -> str:
    if not path.exists():
        raise HTTPException(status_code=404, detail='Document not found')

    content = escape(path.read_text(encoding='utf-8'))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; background: #f5f7fb; color: #18212d; }}
    .wrap {{ max-width: 900px; margin: 0 auto; padding: 32px 20px 56px; }}
    h1 {{ color: #0f1722; margin: 0 0 16px; }}
    p {{ line-height: 1.6; }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      padding: 18px;
      border-radius: 14px;
      border: 1px solid #d7dfeb;
      background: #ffffff;
      color: #18212d;
      line-height: 1.6;
      overflow-x: auto;
    }}
    a {{ color: #0d5ea8; }}
  </style>
</head>
<body>
  <main class="wrap">
    <p><a href="/homepage">Back to homepage</a></p>
    <h1>{escape(title)}</h1>
    <pre>{content}</pre>
  </main>
</body>
</html>
"""


def _sign_ui_session(expires_at: int) -> str:
    secret = settings.ORTY_UI_ADMIN_SECRET
    if not secret:
        raise HTTPException(status_code=503, detail="UI admin login is not configured")
    payload = f"admin:{expires_at}"
    signature = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    token = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii")


def _is_valid_ui_session(token: str | None) -> bool:
    secret = settings.ORTY_UI_ADMIN_SECRET
    if not secret:
        return False
    if not token:
        return False
    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        role, expires_at_raw, signature = decoded.split(":", 2)
        if role != "admin":
            return False
        expires_at = int(expires_at_raw)
    except Exception:
        return False

    expected_payload = f"admin:{expires_at}"
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        expected_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        return False
    return expires_at > int(time.time())


def _is_ui_authenticated(request: Request) -> bool:
    return _is_valid_ui_session(request.cookies.get(UI_SESSION_COOKIE))


def _login_page(error: str | None = None) -> str:
    login_ready = settings.ORTY_UI_ADMIN_SECRET is not None
    error_html = (
        f'<p class="error">{escape(error)}</p>'
        if error
        else '<p class="muted">Sign in as an admin to access the Orty Web UI.</p>'
    )
    disabled_html = (
        '<p class="error">Admin web login is not configured on this deployment.</p>'
        if not login_ready
        else ""
    )
    form_html = (
        """<form method="post" action="/ui/login">
      <label for="shared_secret">Admin secret</label>
      <input id="shared_secret" name="shared_secret" type="password" autocomplete="current-password" required />
      <button type="submit">Enter Orty Web UI</button>
    </form>"""
        if login_ready
        else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Orty Admin Login</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; background: #10131a; color: #e7ecf3; }}
    .container {{ max-width: 420px; margin: 8vh auto; padding: 24px; border-radius: 16px; background: #151c27; border: 1px solid #2a3444; }}
    h1 {{ margin-top: 0; margin-bottom: 8px; }}
    .muted {{ color: #9fa8b5; }}
    .error {{ color: #ffb4ab; }}
    label {{ display: block; margin: 16px 0 8px; }}
    input, button {{ width: 100%; border-radius: 10px; border: 1px solid #2a3444; background: #0f141d; color: #e7ecf3; padding: 12px; box-sizing: border-box; }}
    button {{ margin-top: 16px; cursor: pointer; background: #1f6feb; border-color: #1f6feb; }}
    a {{ color: #8dd0ff; }}
  </style>
</head>
<body>
  <main class="container">
    <p><a href="/homepage">Back to homepage</a></p>
    <h1>Admin Login</h1>
    {error_html}
    {disabled_html}
    {form_html}
  </main>
</body>
</html>
"""


@root_router.get('/', include_in_schema=False)
async def root_to_ui() -> RedirectResponse:
    return RedirectResponse(url='/ui', status_code=307)


@router.get('/login', response_class=HTMLResponse)
async def ui_login() -> str:
    return _login_page()


@router.post('/login')
async def ui_login_submit(
    request: Request,
    shared_secret: str = Form(...),
) -> Response:
    expected_secret = settings.ORTY_UI_ADMIN_SECRET
    if not expected_secret:
        return HTMLResponse(_login_page("Admin web login is not configured."), status_code=503)

    if not hmac.compare_digest(shared_secret, expected_secret):
        return HTMLResponse(_login_page("Invalid admin secret."), status_code=401)

    response = RedirectResponse(url='/ui', status_code=303)
    response.set_cookie(
        key=UI_SESSION_COOKIE,
        value=_sign_ui_session(int(time.time()) + UI_SESSION_TTL_SECONDS),
        max_age=UI_SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return response


@router.post('/logout')
async def ui_logout() -> RedirectResponse:
    response = RedirectResponse(url='/ui/login', status_code=303)
    response.delete_cookie(UI_SESSION_COOKIE)
    return response


@root_router.get('/homepage', response_class=HTMLResponse, include_in_schema=False)
async def homepage() -> str:
    return """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Alfred + Orty</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 0; background: #0f1722; color: #ebf1f6; }
    .wrap { max-width: 760px; margin: 0 auto; padding: 32px 20px 48px; }
    h1 { margin: 0 0 8px; font-size: 2rem; }
    p { line-height: 1.6; color: #c2ccd8; }
    .card { margin-top: 20px; padding: 18px; border-radius: 14px; background: #162131; border: 1px solid #243348; }
    a { color: #8dd0ff; }
  </style>
</head>
<body>
  <main class=\"wrap\">
    <h1>Alfred + Orty</h1>
    <p>
      Alfred is a personal assistant app backed by Orty for private chat, voice, automations,
      and task execution. This site exists to support Alfred's OAuth-based integrations.
    </p>
    <section class=\"card\">
      <strong>Integration scope</strong>
      <p>
        Alfred connects to user-approved services only to deliver assistant features the user asks for,
        including messaging, reminders, home automation, speech, and conversational responses.
      </p>
    </section>
    <section class=\"card\">
      <strong>Policy links</strong>
      <p><a href=\"/privacy-policy\">Privacy Policy</a></p>
      <p><a href=\"/jane-charter\">Jane Charter</a></p>
      <p><a href=\"/voice-and-identity-contract\">Voice And Identity Contract</a></p>
      <p><a href=\"/monetization-guardrails\">Monetization Guardrails</a></p>
      <p><a href=\"/ui\">Orty Web UI</a></p>
    </section>
  </main>
</body>
</html>
"""


@root_router.get('/jane-charter', response_class=HTMLResponse, include_in_schema=False)
async def jane_charter() -> str:
    title, path = _mission_docs()['jane-charter']
    return _render_markdown_document(title, path)


@root_router.get('/voice-and-identity-contract', response_class=HTMLResponse, include_in_schema=False)
async def voice_and_identity_contract() -> str:
    title, path = _mission_docs()['voice-and-identity-contract']
    return _render_markdown_document(title, path)


@root_router.get('/monetization-guardrails', response_class=HTMLResponse, include_in_schema=False)
async def monetization_guardrails() -> str:
    title, path = _mission_docs()['monetization-guardrails']
    return _render_markdown_document(title, path)


@root_router.get('/privacy-policy', response_class=HTMLResponse, include_in_schema=False)
async def privacy_policy() -> str:
    return """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Alfred Privacy Policy</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 0; background: #f5f7fb; color: #18212d; }
    .wrap { max-width: 860px; margin: 0 auto; padding: 32px 20px 56px; }
    h1, h2 { color: #0f1722; }
    p, li { line-height: 1.65; }
  </style>
</head>
<body>
  <main class=\"wrap\">
    <h1>Privacy Policy</h1>
    <p>Effective date: March 20, 2026</p>
    <p>
      Alfred and Orty process user-provided text, voice, and connected-service data only to provide
      assistant features requested by the user.
    </p>
    <h2>What data may be processed</h2>
    <ul>
      <li>Messages, prompts, and assistant replies.</li>
      <li>Voice audio and speech transcripts used for speech recognition and speech synthesis.</li>
      <li>Connected-service metadata needed for requested integrations such as home automation.</li>
      <li>Configuration details the user provides, such as assistant preferences and saved places.</li>
    </ul>
    <h2>How data is used</h2>
    <ul>
      <li>To respond to user requests and execute requested actions.</li>
      <li>To provide connected features such as reminders, home automation, and voice interaction.</li>
      <li>To improve reliability, debug failures, and maintain service operation.</li>
    </ul>
    <h2>Sharing</h2>
    <p>
      Data is shared only with the service providers required to fulfill user-requested features,
      such as speech, language, or home automation providers configured by the user.
    </p>
    <h2>Retention and control</h2>
    <p>
      Users control their connected accounts and can revoke access by removing integrations or
      deleting locally stored settings and credentials.
    </p>
    <h2>Contact</h2>
    <p>
      For questions about Alfred or Orty privacy handling, contact the operator of the deployed service.
    </p>
  </main>
</body>
</html>
"""


@router.post('/chat', response_model=ChatResponse)
async def ui_chat(payload: ChatRequest, request: Request):
    if not _is_ui_authenticated(request):
        raise HTTPException(status_code=401, detail='Unauthorized')

    runtime = get_runtime(request)
    primary = ensure_primary_client(request)
    admin_client = {**primary, "is_admin": True}
    incoming_conversation_id = None if payload.reset_conversation else payload.conversation_id
    conversation_id = runtime.memory_store.ensure_conversation_id(incoming_conversation_id)

    history = runtime.memory_store.get_recent_messages(
        conversation_id,
        limit=payload.history_limit,
        client_id=admin_client['client_id'],
    )
    effective_history = [
        *history,
        *[{"role": msg.role, "content": msg.content} for msg in payload.recent_messages],
    ]
    reply = await runtime.ai_service.generate(
        payload.message,
        history=effective_history,
        request_context=ChatRequestContext(
            channel="orty_web_ui",
            conversation_id=conversation_id,
            auth_method="admin-ui",
            current_client=admin_client,
            requested_client_name="orty-web-ui",
            assistant_name="Orty",
            personality_preset=payload.personality_preset,
            client_system_prompt=payload.system_prompt,
        ),
    )

    if payload.persist:
        runtime.memory_store.append_message(conversation_id, 'user', payload.message, client_id=admin_client['client_id'])
        runtime.memory_store.append_message(conversation_id, 'assistant', reply, client_id=admin_client['client_id'])

    return ChatResponse(reply=reply, conversation_id=conversation_id, used_history=len(history))


@router.get('', response_class=HTMLResponse)
@router.get('/', response_class=HTMLResponse)
async def ui_home(request: Request) -> Response:
    if not _is_ui_authenticated(request):
        return RedirectResponse(url='/ui/login', status_code=303)

    return """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Orty Web UI</title>
  <style>
    :root { color-scheme: light dark; }
    body { font-family: Arial, sans-serif; margin: 0; background: #10131a; color: #e7ecf3; }
    .container { max-width: 880px; margin: 0 auto; padding: 20px; }
    h1 { margin: 0 0 4px; }
    .muted { color: #9fa8b5; margin-bottom: 16px; }
    .controls { display: grid; gap: 10px; grid-template-columns: 1fr auto; margin-bottom: 10px; }
    input, textarea, button { border-radius: 8px; border: 1px solid #2a3444; background: #151c27; color: #e7ecf3; }
    input, textarea { padding: 10px; }
    textarea { width: 100%; min-height: 80px; resize: vertical; }
    button { padding: 10px 14px; cursor: pointer; }
    #chat-log { border: 1px solid #2a3444; border-radius: 10px; min-height: 260px; padding: 12px; background: #0f141d; overflow-y: auto; }
    .msg { margin: 10px 0; white-space: pre-wrap; }
    .user strong { color: #7cc5ff; }
    .assistant strong { color: #9de284; }
    .meta { margin-top: 8px; color: #9fa8b5; font-size: 0.9rem; }
  </style>
</head>
<body>
  <div class=\"container\">
    <h1>Orty Web UI</h1>
    <p class=\"muted\">Admin-authenticated Orty chat interface with conversation continuity.</p>
    <form method=\"post\" action=\"/ui/logout\" style=\"margin-bottom:16px;\">
      <button type=\"submit\" style=\"width:auto;\">Log out</button>
    </form>

    <div class=\"controls\">
      <input id=\"conversation-id\" type=\"text\" placeholder=\"conversation_id (optional)\" />
      <button id=\"clear\" type=\"button\">New Conversation</button>
    </div>

    <div id=\"chat-log\"></div>

    <form id=\"chat-form\" style=\"margin-top:12px;\">
      <textarea id=\"message\" placeholder=\"Type a message...\" required></textarea>
      <button type=\"submit\" style=\"margin-top:8px;\">Send</button>
    </form>

    <div class=\"meta\" id=\"status\">Ready</div>
  </div>

  <script>
    const conversationInput = document.getElementById('conversation-id');
    const chatForm = document.getElementById('chat-form');
    const messageInput = document.getElementById('message');
    const chatLog = document.getElementById('chat-log');
    const statusEl = document.getElementById('status');
    const clearButton = document.getElementById('clear');

    const savedConversation = localStorage.getItem('orty.conversation_id');
    if (savedConversation) conversationInput.value = savedConversation;

    function appendMessage(role, text) {
      const div = document.createElement('div');
      div.className = `msg ${role}`;
      const label = document.createElement('strong');
      label.textContent = role === 'user' ? 'You:' : 'Orty:';
      div.appendChild(label);
      div.appendChild(document.createTextNode(` ${text}`));
      chatLog.appendChild(div);
      chatLog.scrollTop = chatLog.scrollHeight;
    }

    clearButton.addEventListener('click', () => {
      conversationInput.value = '';
      localStorage.removeItem('orty.conversation_id');
      statusEl.textContent = 'Started a new conversation (new id will be assigned on next message).';
    });

    chatForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const message = messageInput.value.trim();
      const conversation_id = conversationInput.value.trim();

      if (!message) return;

      appendMessage('user', message);
      messageInput.value = '';
      statusEl.textContent = 'Sending...';

      try {
        const payload = { message };
        if (conversation_id) payload.conversation_id = conversation_id;

        const response = await fetch('/ui/chat', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        });

        const body = await response.json();
        if (!response.ok) {
          if (response.status === 401) {
            window.location.href = '/ui/login';
            return;
          }
          appendMessage('assistant', `Error: ${body.detail || response.status}`);
          statusEl.textContent = `Request failed (${response.status}).`;
          return;
        }

        appendMessage('assistant', body.reply);

        if (body.conversation_id) {
          conversationInput.value = body.conversation_id;
          localStorage.setItem('orty.conversation_id', body.conversation_id);
        }

        statusEl.textContent = 'Reply received.';
      } catch (error) {
        appendMessage('assistant', `Network error: ${error.message}`);
        statusEl.textContent = 'Network error.';
      }
    });
  </script>
</body>
</html>
"""
