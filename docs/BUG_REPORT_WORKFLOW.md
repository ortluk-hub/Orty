# Complete Bug Report Workflow

## End-to-End Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         BUG REPORT WORKFLOW                               │
└──────────────────────────────────────────────────────────────────────────┘

┌─────────────┐
│   Alfred    │  (Android App - User's Device)
│   User says: "Report a bug"
└──────┬──────┘
       │
       │ 1. User voice command: "The wake word only worked once today"
       │
       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Alfred captures:                                                        │
│  • Summary from user's description                                       │
│  • Recent conversation history                                           │
│  • Device info (Android version, app version, device model)             │
│  • Orty configuration status                                             │
└─────────────────────────────────────────────────────────────────────────┘
       │
       │ 2. POST /v1/bug-reports
       │    {
       │      "title": "Wake word detection failed",
       │      "summary": "Wake word only worked once today",
       │      "details": "...",
       │      "metadata": {
       │        "device": "Pixel 8",
       │        "app_version": "1.2.3",
       │        "android_release": "14"
       │      }
       │    }
       │
       ▼
┌─────────────┐
│    Orty     │  (Server - Your Infrastructure)
└──────┬──────┘
       │
       │ 3a. Store in SQLite
       │     INSERT INTO bug_reports (...)
       │     → report_id: "uuid-123"
       │
       │ 3b. Forward to Codey (if configured)
       │     POST http://codey:8000/tasks
       │     {
       │       "task_type": "bug_report",
       │       "source_product": "alfred",
       │       "title": "Wake word detection failed",
       │       "workspace_ref": "/path/to/Alfred",
       │       "task_payload": {
       │         "orty_report_id": "uuid-123",
       │         "approval_mode": "orty_supervised"
       │       }
       │     }
       │     → task_id: "codey-task-456"
       │
       │ 3c. Update bug status
       │     bug_reports.codey_task_id = "codey-task-456"
       │     bug_reports.status = "in_codey_processing"
       │
       ▼
┌─────────────┐
│    Codey    │  (Worker - Your Infrastructure)
│   Status: queued
└──────┬──────┘
       │
       │ 4. Triage Phase
       │    - Read bug report
       │    - Analyze workspace (Alfred codebase)
       │    - Identify likely cause
       │    - Assess confidence & complexity
       │
       │    Event: TASK_TRIAGED
       │    {
       │      "confidence": 0.82,
       │      "complexity": "small",
       │      "root_cause": "WakeWordDetector.kt line 45",
       │      "risk_notes": []
       │    }
       │
       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Orty Supervisor Decision Point                                         │
│                                                                         │
│  Evaluates:                                                             │
│  • confidence ≥ 75%? ✓ (0.82)                                          │
│  • complexity ≤ "small"? ✓ (small)                                     │
│  • High-risk keywords? ✗ (none)                                        │
│                                                                         │
│  Decision: AUTO-APPROVE                                                 │
└─────────────────────────────────────────────────────────────────────────┘
       │
       │ 5. Orty approves on behalf of user
       │    POST /tasks/{task_id}/approve
       │    {"approved_by": "orty_supervisor"}
       │
       │    Event: PLAN_APPROVED
       │
       ▼
┌─────────────┐
│    Codey    │  Status: plan_approved → executing
└──────┬──────┘
       │
       │ 6. Execution Phase
       │    - Apply patch to Alfred workspace
       │    - Fix: WakeWordDetector.kt line 45
       │      ```kotlin
       │      - if (confidence > 0.5) {
       │      + if (confidence > 0.3) {
       │      ```
       │
       │    Event: EXECUTION_SUCCESS
       │
       │ 7. Verification Phase
       │    - Run Alfred tests
       │    - ./gradlew test
       │    - Check build passes
       │
       │    Event: VERIFICATION_PASSED
       │    {
       │      "command_type": "test",
       │      "exit_code": 0,
       │      "duration_ms": 45230
       │    }
       │
       │    Status: completed
       │
       ▼
┌─────────────┐
│    Orty     │
└──────┬──────┘
       │
       │ 8. Update bug status
       │     bug_reports.status = "fixed_verified"
       │     bug_reports.codey_status = "completed"
       │
       │ 9. Notify user (via admin channel)
       │    "Bug fix verified and completed successfully!"
       │
       ▼
┌─────────────┐
│    Alfred   │
│   User sees: "Your bug report has been fixed!"
└─────────────┘
```

## Alternative Path: High-Risk Fix Requires User Approval

```
┌─────────────────────────────────────────────────────────────────────────┐
│  HIGH-RISK SCENARIO                                                      │
└─────────────────────────────────────────────────────────────────────────┘

Codey Triage Result:
{
  "confidence": 0.65,           // Below 75% threshold
  "complexity": "large",        // Above "small" threshold
  "risk_notes": [
    "Breaking change to API",
    "Requires database migration"
  ]
}

       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Orty Supervisor Decision Point                                         │
│                                                                         │
│  Evaluates:                                                             │
│  • confidence ≥ 75%? ✗ (0.65)                                          │
│  • complexity ≤ "small"? ✗ (large)                                     │
│  • High-risk keywords? ✓ ("breaking", "migration")                     │
│                                                                         │
│  Decision: REQUEST USER APPROVAL                                        │
└─────────────────────────────────────────────────────────────────────────┘
       │
       │ 5a. Orty notifies user via admin channel
       │
       │    Admin Channel Options:
       │    • Web UI notification
       │    • Conversation message
       │    • Bot event
       │
       │    Message:
       │    "🔧 Bug Fix Requires Approval
       │
       │     Bug: uuid-123
       │     Plan: Refactor wake word detector with API changes
       │     Confidence: 65%
       │     Complexity: large
       │     Risks: Breaking change to API, Requires database migration
       │
       │     Reply 'approve codey-task-456' to approve this fix."
       │
       │ 5b. Bug status updated
       │     bug_reports.status = "waiting_user_approval"
       │
       ▼
┌─────────────┐
│    User     │  (Admin Client)
└──────┬──────┘
       │
       │ 6a. User reviews plan
       │    GET /tasks/codey-task-456
       │    GET /tasks/codey-task-456/artifacts/fix_plan
       │
       │ 6b. User approves
       │    POST /tasks/codey-task-456/approve
       │    {"approved_by": "user-admin-xyz"}
       │
       │    OR via conversation:
       │    User: "approve codey-task-456"
       │
       ▼
┌─────────────┐
│    Orty     │
└──────┬──────┘
       │
       │ 7. Forward approval to Codey
       │    (same as step 5 in auto-approve flow)
       │
       ▼
┌─────────────┐
│    Codey    │  (continues to execution)
└─────────────┘
```

## Admin Channel Integration

### For Registered Clients (Promotion System)

```
┌─────────────┐
│   Client    │  (e.g., mobile app, desktop client)
└──────┬──────┘
       │
       │ 1. Request admin status
       │    POST /v1/clients/me/promotion/request
       │    {
       │      "reason": "I need to approve bug fixes for my team",
       │      "admin_secret_hash": "sha256(OrtyIAmYourFather)"
       │    }
       │
       ▼
┌─────────────┐
│    Orty     │
│  Status: pending
└──────┬──────┘
       │
       │ 2. Existing admin reviews
       │    GET /v1/clients/promotion/requests
       │    → [{"request_id": "req-123", "client_name": "My App"}]
       │
       │ 3. Admin approves
       │    POST /v1/clients/promotion/approve
       │    {"request_id": "req-123"}
       │
       ▼
┌─────────────┐
│   Client    │  Now has is_admin: true
└──────┬──────┘
       │
       │ 4. Client can now:
       │    • Approve high-risk bug fixes
       │    • View all bug reports
       │    • Manage other clients
       │    • Access admin endpoints
       │
       │ 5. Bug approval workflow
       │    GET /v1/clients/promotion/requests  # Check pending
       │    POST /v1/clients/promotion/approve  # Approve fix
       │
       ▼
┌─────────────┐
│    Orty     │  Forwards to Codey
└─────────────┘
```

## Status Transitions

### Bug Report Status Flow

```
new
  ↓
in_codey_processing  ← Orty forwarded to Codey
  ↓
triaged              ← Codey analyzed the bug
  ↓
planned              ← Fix plan created
  ↓
  ├─→ auto_approved_by_orty      ← Low risk, Orty approved
  │         ↓
  ├─→ waiting_user_approval      ← High risk, waiting for user
  │         ↓
  │     plan_approved            ← User approved
  │         ↓
  └─→ plan_rejected              ← User/admin rejected
            ↓
  fix_in_progress        ← Codey applying patch
  ↓
verifying              ← Running tests
  ↓
  ├─→ fixed_verified           ← Tests passed ✓
  │
  └─→ fix_verification_failed  ← Tests failed ✗
            ↓
        (back to planned or failed)
```

### Codey Task Status Flow

```
queued
  ↓
triaged                ← TASK_TRIAGED event
  ↓
planned                ← PLAN_CREATED event
  ↓
  ├─→ plan_approved    ← PLAN_APPROVED event
  │       ↓
  └─→ plan_rejected    ← PLAN_REJECTED event
          ↓
executing              ← EXECUTION_STARTED event
  ↓
verifying              ← EXECUTION_SUCCESS event
  ↓
  ├─→ completed        ← VERIFICATION_PASSED event
  │
  └─→ verification_failed  ← VERIFICATION_FAILED event
          ↓
      (can retry or fail)
```

## API Endpoints Used

### Bug Report Endpoints (Orty)

```bash
# Submit bug report (Alfred → Orty)
POST /v1/bug-reports
-H "X-Orty-Secret: OrtyIAmYourFather"
-H "Content-Type: application/json"

# List bug reports
GET /v1/bug-reports
-H "X-Orty-Secret: OrtyIAmYourFather"

# Get bug report by ID
GET /v1/bug-reports/{report_id}
```

### Codey Task Endpoints

```bash
# Create task (Orty → Codey) - automatic
POST /tasks
{
  "task_type": "bug_report",
  "source_product": "alfred",
  "title": "...",
  "workspace_ref": "/path/to/Alfred"
}

# Get task status
GET /tasks/{task_id}

# Get task events
GET /tasks/{task_id}/events

# Trigger triage
POST /tasks/{task_id}/triage

# Trigger planning
POST /tasks/{task_id}/plan

# Approve plan
POST /tasks/{task_id}/approve
{"approved_by": "orty_supervisor"}

# Get artifacts
GET /tasks/{task_id}/artifacts
GET /tasks/{task_id}/artifacts/fix_plan
```

### Admin/Promotion Endpoints (Orty)

```bash
# Request admin status
POST /v1/clients/me/promotion/request
{
  "reason": "...",
  "admin_secret_hash": "sha256(...)"
}

# List promotion requests (admin only)
GET /v1/clients/promotion/requests?status=pending

# Approve promotion (admin only)
POST /v1/clients/promotion/approve
{"request_id": "..."}

# Check your admin status
GET /v1/auth/me
→ {"is_admin": true}
```

## Configuration Required

### Orty (.env)

```bash
# Codey integration
CODEY_URL=http://127.0.0.1:8000
CODEY_API_KEY=orty-service-key
CODEY_ALFRED_WORKSPACE=/home/ortluk/ortluk-hub/Alfred/Alfred

# Supervisor settings
CODEY_AUTO_APPROVE_LOW_RISK=true
CODEY_REQUIRE_APPROVAL_HIGH_RISK=true
CODEY_NOTIFY_USER_ON_PLAN=true

# Admin secret (for promotion system)
ORTY_SHARED_SECRET=OrtyIAmYourFather
```

### Codey (optional)

```bash
# Ollama configuration
CODY_OLLAMA_PRIMARY_URL=http://127.0.0.1:11434
CODY_OLLAMA_PRIMARY_MODEL=qwen3-coder:480b-cloud
```

## Monitoring & Observability

### Check Bug Report Status

```bash
# Orty bug reports
curl http://localhost:8080/v1/bug-reports \
  -H "X-Orty-Secret: OrtyIAmYourFather"

# Codey tasks
curl http://localhost:8000/tasks

# Specific task events
curl http://localhost:8000/tasks/{task_id}/events
```

### Dashboard

- **Codey Dashboard**: http://localhost:8000/dashboard
  - Task statistics
  - Recent tasks
  - Task details

- **Orty Web UI**: http://localhost:8080/
  - Chat interface
  - Admin panel (for admin clients)

## Example: Complete cURL Workflow

```bash
# 1. Submit bug report to Orty
BUG_RESPONSE=$(curl -s -X POST http://localhost:8080/v1/bug-reports \
  -H "Content-Type: application/json" \
  -H "X-Orty-Secret: OrtyIAmYourFather" \
  -d '{
    "title": "Test Bug",
    "summary": "Testing workflow",
    "details": "This is a test",
    "metadata": {"test": "true"}
  }')

REPORT_ID=$(echo $BUG_RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['report_id'])")
echo "Bug report created: $REPORT_ID"

# 2. Check bug was forwarded to Codey
sleep 2  # Give Orty time to forward
curl http://localhost:8000/tasks | python3 -m json.tool

# 3. Find the task ID
TASK_ID=$(curl -s http://localhost:8000/tasks | \
  python3 -c "import sys,json; tasks=json.load(sys.stdin); print([t['task_id'] for t in tasks if 'Test Bug' in t.get('title','')][0] if tasks else '')")

if [ -n "$TASK_ID" ]; then
  echo "Task created: $TASK_ID"

  # 4. Trigger triage
  curl -s -X POST "http://localhost:8000/tasks/$TASK_ID/triage"

  # 5. Wait for triage, then trigger planning
  sleep 5
  curl -s -X POST "http://localhost:8000/tasks/$TASK_ID/plan"

  # 6. Check plan
  curl "http://localhost:8000/tasks/$TASK_ID/artifacts/fix_plan" | python3 -m json.tool

  # 7. Approve plan (as Orty supervisor)
  curl -s -X POST "http://localhost:8000/tasks/$TASK_ID/approve" \
    -H "Content-Type: application/json" \
    -d '{"approved_by": "orty_supervisor"}'

  # 8. Track to completion
  while true; do
    STATUS=$(curl -s "http://localhost:8000/tasks/$TASK_ID" | \
      python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))")
    echo "Task status: $STATUS"

    if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
      break
    fi

    sleep 2
  done

  # 9. Check final result
  curl "http://localhost:8000/tasks/$TASK_ID/events" | python3 -m json.tool
fi

# 10. Check bug report status in Orty
curl "http://localhost:8080/v1/bug-reports" \
  -H "X-Orty-Secret: OrtyIAmYourFather" | python3 -m json.tool
```

## Summary

### Low-Risk Bug (Auto-Approved)
1. Alfred → Orty (bug report)
2. Orty → Codey (task creation)
3. Codey triages → Orty auto-approves
4. Codey executes → verifies → completes
5. Orty notifies user

### High-Risk Bug (User Approval)
1. Alfred → Orty (bug report)
2. Orty → Codey (task creation)
3. Codey triages → Orty requests user approval
4. User reviews → approves via admin channel
5. Codey executes → verifies → completes
6. Orty notifies user

### Admin Client Workflow
1. Client requests admin status (with secret hash)
2. Existing admin approves
3. New admin can approve high-risk bug fixes
4. Multiple admins can manage the system

See also:
- `docs/ORTY_CODEY_INTEGRATION.md` - Orty-Codey setup
- `docs/CLIENT_PROMOTION_SYSTEM.md` - Admin promotion
- `EVOLUTION_CHANGELOG.md` - Change log
