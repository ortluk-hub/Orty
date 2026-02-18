from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix='/ui', tags=['ui'])


@router.get('', response_class=HTMLResponse)
async def ui_home() -> str:
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
    .controls { display: grid; gap: 10px; grid-template-columns: 1fr 1fr auto; margin-bottom: 10px; }
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
    <p class=\"muted\">Simple testing interface for chat + conversation continuity.</p>

    <div class=\"controls\">
      <input id=\"secret\" type=\"password\" placeholder=\"x-orty-secret\" />
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
    const secretInput = document.getElementById('secret');
    const conversationInput = document.getElementById('conversation-id');
    const chatForm = document.getElementById('chat-form');
    const messageInput = document.getElementById('message');
    const chatLog = document.getElementById('chat-log');
    const statusEl = document.getElementById('status');
    const clearButton = document.getElementById('clear');

    const savedSecret = localStorage.getItem('orty.secret');
    const savedConversation = localStorage.getItem('orty.conversation_id');
    if (savedSecret) secretInput.value = savedSecret;
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
      const secret = secretInput.value.trim();
      const conversation_id = conversationInput.value.trim();

      if (!message) return;
      if (!secret) {
        statusEl.textContent = 'Please provide x-orty-secret first.';
        return;
      }

      localStorage.setItem('orty.secret', secret);
      appendMessage('user', message);
      messageInput.value = '';
      statusEl.textContent = 'Sending...';

      try {
        const payload = { message };
        if (conversation_id) payload.conversation_id = conversation_id;

        const response = await fetch('/chat', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-orty-secret': secret,
          },
          body: JSON.stringify(payload),
        });

        const body = await response.json();
        if (!response.ok) {
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
