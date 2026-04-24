# Orty-Codey Integration Setup Guide

This guide explains how to set up automated bug report processing from Alfred → Orty → Codey.

## Architecture

```
┌─────────┐     ┌─────────┐     ┌─────────┐
│ Alfred  │ ──→ │  Orty   │ ──→ │  Codey  │
│ (Android)│     │ (Server)│     │ (Worker)│
└─────────┘     └─────────┘     └─────────┘
     │               │               │
     │               │               │
     ▼               ▼               ▼
  Voice command  Store bug      Triage & fix
  "report bug"   Forward to     Apply patches
                 Codey          Run tests
```

## Quick Start

### 1. Start Codey Server

Codey must be running as an HTTP server to receive bug reports from Orty.

```bash
cd /home/ortluk/ortluk-hub/Codey

# Activate virtual environment
source .venv/bin/activate  # or activate your venv

# Start Codey API server on port 8000
python -m codey.api_ui --host 0.0.0.0 --port 8000
```

**Verify Codey is running:**
```bash
curl http://localhost:8000/health
# Expected: {"status": "ok", ...}
```

### 2. Configure Orty

Update Orty's `.env` file with Codey settings:

```bash
cd /home/ortluk/ortluk-hub/orty/Orty

# Edit .env file (already configured with defaults)
# CODEY_URL=http://127.0.0.1:8000
# CODEY_API_KEY=orty-service-key
# CODEY_ALFRED_WORKSPACE=/home/ortluk/ortluk-hub/Alfred/Alfred
```

### 3. Start Orty Server

```bash
cd /home/ortluk/ortluk-hub/orty/Orty

# Activate virtual environment
source .venv/bin/activate

# Install dependencies if needed
pip install -r requirements.txt

# Start Orty server
python -m uvicorn service.api:app --host 0.0.0.0 --port 8080 --reload
```

**Verify Orty is running:**
```bash
curl http://localhost:8080/health
# Expected: {"status": "ok", "assistant": "Orty"}
```

### 4. Test Bug Report Submission

```bash
# Submit a test bug report to Orty
curl -X POST http://localhost:8080/v1/bug-reports \
  -H "Content-Type: application/json" \
  -H "X-Orty-Secret: OrtyIAmYourFather" \
  -d '{
    "client": "test-client",
    "title": "Test Bug Report",
    "summary": "Testing Orty-Codey integration",
    "details": "This is a test bug report to verify the integration works.",
    "metadata": {
      "test": "true"
    }
  }'

# Expected response: {"status": "ok", "report_id": "..."}
```

### 5. Verify Codey Received the Task

```bash
# List tasks in Codey
curl http://localhost:8000/tasks

# Should show the new bug report task
```

## Configuration Options

### Orty Settings (.env)

| Variable | Description | Default |
|----------|-------------|---------|
| `CODEY_URL` | Codey API base URL | `http://127.0.0.1:8000` |
| `CODEY_API_KEY` | Optional API key for auth | `orty-service-key` |
| `CODEY_ALFRED_WORKSPACE` | Path to Alfred workspace | `/home/ortluk/ortluk-hub/Alfred/Alfred` |

### Codey Settings

Codey uses environment variables or defaults:

| Variable | Description | Default |
|----------|-------------|---------|
| `CODY_OLLAMA_PRIMARY_URL` | Ollama server URL | `http://127.0.0.1:11434` |
| `CODY_OLLAMA_PRIMARY_MODEL` | Primary LLM model | `qwen3-coder:480b-cloud` |

## How It Works

### Bug Report Flow

1. **Alfred** (Android app) captures bug report via voice command
2. **Alfred** sends bug report to Orty's `/v1/bug-reports` endpoint
3. **Orty** stores bug report in SQLite database
4. **Orty** automatically forwards bug to Codey via HTTP POST `/tasks`
5. **Codey** creates a new task with status "queued"
6. **Codey** triages the bug report (read-only analysis)
7. **Codey** creates a fix plan
8. **Codey** auto-approves plan if confidence is high enough
9. **Codey** applies patches to Alfred workspace
10. **Codey** runs verification tests
11. **Codey** updates task status to "completed" or "failed"

### Auto-Approval Rules

Codey auto-approves bug fixes when:
- Confidence ≥ 75%
- Risk level is "low" or "medium"
- Complexity is "trivial" or "small"
- Product is in auto-approve list (default: "alfred")

Manual review is required for:
- High-risk changes
- Large complexity
- Critical systems
- Low confidence plans

## Monitoring

### Check Task Status

```bash
# Get task details
curl http://localhost:8000/tasks/{task_id}

# Get task events
curl http://localhost:8000/tasks/{task_id}/events

# List all tasks
curl http://localhost:8000/tasks
```

### View Codey Dashboard

Open in browser: `http://localhost:8000/dashboard`

The dashboard shows:
- Task statistics (queued, in-progress, completed, failed)
- Recent tasks with status badges
- Task details and artifacts

### Check Orty Bug Reports

```bash
# List bug reports
curl http://localhost:8080/v1/bug-reports \
  -H "X-Orty-Secret: OrtyIAmYourFather"
```

## Troubleshooting

### Codey Not Receiving Bugs

1. **Check Codey is running:**
   ```bash
   curl http://localhost:8000/health
   ```

2. **Verify Orty configuration:**
   ```bash
   cat /home/ortluk/ortluk-hub/orty/Orty/.env | grep CODEY
   ```

3. **Check Orty logs for errors:**
   ```bash
   # Look for "Failed to submit bug report" errors
   ```

### Task Stuck in "queued" Status

Tasks may be queued if:
- No worker is available to triage
- LLM provider is unavailable
- Workspace path is invalid

**Solution:**
```bash
# Manually trigger triage
curl -X POST http://localhost:8000/tasks/{task_id}/triage
```

### Auto-Approval Not Working

Check auto-approval configuration in `src/cody/orty_integration.py`:

```python
AutoApprovalConfig(
    auto_approve_confidence_threshold=0.75,
    auto_approve_max_risk="low",
    auto_approve_max_complexity="small",
    auto_approve_products=["alfred"],
)
```

## Production Deployment

### Docker Setup

For production, run Orty and Codey in Docker containers:

```yaml
# docker-compose.yml
version: '3.8'
services:
  codey:
    build: ./Codey
    ports:
      - "8000:8000"
    volumes:
      - ./Alfred:/workspaces/alfred
    environment:
      - CODY_OLLAMA_PRIMARY_URL=http://ollama:11434

  orty:
    build: ./Orty
    ports:
      - "8080:8080"
    environment:
      - CODEY_URL=http://codey:8000
      - CODEY_ALFRED_WORKSPACE=/workspaces/alfred
    volumes:
      - ./Alfred:/workspaces/alfred
    depends_on:
      - codey

  ollama:
    image: ollama/ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama

volumes:
  ollama_data:
```

### Security Considerations

1. **API Authentication**: Set strong `CODEY_API_KEY`
2. **Network Isolation**: Run Orty and Codey in private network
3. **Workspace Permissions**: Restrict Codey's write access to specific directories
4. **Rate Limiting**: Configure rate limits for bug report submissions

## Next Steps

1. **Configure Alfred**: Point Alfred's Orty base URL to your Orty server
2. **Set up monitoring**: Add logging and alerting for failed bug reports
3. **Tune auto-approval**: Adjust thresholds based on your team's risk tolerance
4. **Add notifications**: Integrate with Slack/Email for bug status updates
