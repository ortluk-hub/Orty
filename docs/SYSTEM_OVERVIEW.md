# Orty Bug Management System - Complete Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    BUG MANAGEMENT ECOSYSTEM                              │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│   Alfred    │  ─────→ │    Orty     │  ─────→ │    Codey    │
│  (Android)  │  HTTP   │  (Server)   │  HTTP   │  (Worker)   │
└─────────────┘         └─────────────┘         └─────────────┘
     │                        │                        │
     │ Voice UI               │ Storage                │ LLM + Tools
     │ Bug capture            │ Supervision            │ Triage + Fix
     │ Email draft            │ Admin channels         │ Docker sandbox
     │                        │ Client management      │
     └────────────────────────┴────────────────────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │   PostgreSQL/   │
                     │   SQLite DB     │
                     │                 │
                     │ - bug_reports   │
                     │ - clients       │
                     │ - promotion_req │
                     │ - tasks         │
                     └─────────────────┘
```

## Components

### 1. Alfred (Android App)
- **Location**: `/home/ortluk/ortluk-hub/Alfred/Alfred`
- **Role**: Bug capture interface
- **Key Files**:
  - `AndroidBugReportHandler.kt` - Capture and submit bugs
  - `RetrofitOrtyGateway.kt` - HTTP client for Orty

**Workflow**:
```kotlin
// User says: "Report a bug"
val action = SupportedAction.ReportBug("Wake word failed")
val result = bugReportHandler.submit(action)
// → Opens email draft
// → Submits to Orty (background)
```

### 2. Orty (Server)
- **Location**: `/home/ortluk/ortluk-hub/orty/Orty`
- **Role**: Storage, supervision, admin management
- **Key Files**:
  - `service/storage/bug_reports_repo.py` - Bug storage
  - `service/integrations/bug_report_processor.py` - Codey integration
  - `service/integrations/codey_client.py` - Codey HTTP client
  - `service/storage/clients_repo.py` - Client promotion system
  - `service/api/routes/v1_bug_reports.py` - Bug API
  - `service/api/routes/v1_clients.py` - Promotion API

**Workflow**:
```python
# 1. Store bug
record = bug_reports_repo.create_report(...)

# 2. Forward to Codey
task = codey_client.submit_bug_report(...)

# 3. Supervise (auto-approve or request user approval)
if low_risk:
    codey_client.approve_plan(task_id, approved_by="orty_supervisor")
else:
    notify_user_for_approval(...)
```

### 3. Codey (Worker)
- **Location**: `/home/ortluk/ortluk-hub/Codey`
- **Role**: Bug triage, planning, fixing, verification
- **Key Files**:
  - `src/cody/orty_integration.py` - Backlog processing
  - `src/cody/tasks.py` - Task storage
  - `src/cody/api_ui.py` - HTTP API
  - `src/cody/triage.py` - Bug analysis
  - `src/cody/planning.py` - Fix planning
  - `src/cody/sandbox.py` - Patch execution

**Workflow**:
```python
# 1. Receive bug task
task = task_store.create_task({...})

# 2. Triage
triage_artifact = triage.triage_bug_report(task)

# 3. Plan
fix_plan = planning.create_fix_plan(task, triage_artifact)

# 4. Wait for approval (Orty supervises)

# 5. Execute
patches.apply_patches(task.workspace_ref, fix_plan.patches)

# 6. Verify
result = run_verification(task.workspace_ref, "test", "./gradlew test")
```

## Workflows

### Individual Bug Flow (Real-Time)

```
1. Alfred → Orty (POST /v1/bug-reports)
2. Orty stores bug in SQLite
3. Orty → Codey (POST /tasks)
4. Codey triages
5. Orty auto-approves (low risk) OR requests user approval (high risk)
6. Codey executes fix
7. Codey verifies
8. Orty updates bug status
9. Orty notifies user
```

### Backlog Processing Flow (Batch)

```
1. Admin runs: ./scripts/process_backlog.sh
2. Script fetches pending bugs from Orty
3. BacklogProcessor scans bugs
4. For each bug:
   a. Submit to Codey
   b. Track to triage
   c. Auto-approve if eligible
   d. Track to completion
5. Generate summary report
```

### Client Promotion Flow

```
1. Client requests admin status
   POST /v1/clients/me/promotion/request
   {reason: "...", admin_secret_hash: "sha256(...)"}

2. Existing admin reviews
   GET /v1/clients/promotion/requests

3. Admin approves
   POST /v1/clients/promotion/approve

4. Client becomes admin (is_admin: true)

5. New admin can approve high-risk bug fixes
```

## API Endpoints

### Bug Reports (Orty)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/v1/bug-reports` | Admin secret | Submit bug |
| GET | `/v1/bug-reports` | Admin secret | List bugs |
| GET | `/v1/bug-reports/{id}` | Admin secret | Get bug |

### Task Management (Codey)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/tasks` | API key | Create task |
| GET | `/tasks/{id}` | API key | Get task |
| GET | `/tasks/{id}/events` | API key | Get events |
| POST | `/tasks/{id}/triage` | API key | Trigger triage |
| POST | `/tasks/{id}/plan` | API key | Create plan |
| POST | `/tasks/{id}/approve` | API key | Approve plan |
| GET | `/tasks` | API key | List tasks |

### Client Promotion (Orty)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/v1/clients/me/promotion/request` | Bearer | Request admin |
| GET | `/v1/clients/promotion/requests` | Admin | List requests |
| POST | `/v1/clients/promotion/approve` | Admin | Approve request |
| POST | `/v1/clients/promotion/reject` | Admin | Reject request |
| GET | `/v1/clients/admin/list` | Admin | List admins |
| GET | `/v1/auth/me` | Bearer | Get client info |

## Configuration

### Orty (.env)

```bash
# Core
ORTY_SHARED_SECRET=OrtyIAmYourFather
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
SQLITE_PATH=data/orty.db

# Codey Integration
CODEY_URL=http://127.0.0.1:8000
CODEY_API_KEY=orty-service-key
CODEY_ALFRED_WORKSPACE=/home/ortluk/ortluk-hub/Alfred/Alfred

# Supervisor Settings
CODEY_AUTO_APPROVE_LOW_RISK=true
CODEY_REQUIRE_APPROVAL_HIGH_RISK=true
CODEY_NOTIFY_USER_ON_PLAN=true
```

### Codey (environment)

```bash
CODY_OLLAMA_PRIMARY_URL=http://127.0.0.1:11434
CODY_OLLAMA_PRIMARY_MODEL=qwen3-coder:480b-cloud
```

## Scripts

### Process Backlog
```bash
cd /home/ortluk/ortluk-hub/orty/Orty
./scripts/process_backlog.sh pending
```

### Test Integration
```bash
cd /home/ortluk/ortluk-hub/orty/Orty
./test_integration.sh
```

### Start Codey Server
```bash
cd /home/ortluk/ortluk-hub/Codey
./start_codey_server.sh
```

## Status States

### Bug Report Status
- `pending` - New bug, not yet processed
- `in_codey_processing` - Submitted to Codey
- `triaged` - Codey analyzed
- `planned` - Fix plan created
- `auto_approved_by_orty` - Orty auto-approved (low risk)
- `waiting_user_approval` - Awaiting user approval (high risk)
- `plan_approved` - Plan approved
- `fix_in_progress` - Codey applying patch
- `fixed_verified` - Complete ✓
- `fix_verification_failed` - Tests failed ✗
- `plan_rejected` - Plan rejected
- `failed` - Processing failed

### Codey Task Status
- `queued` - Waiting to be processed
- `triaged` - Analysis complete
- `planned` - Plan created
- `plan_approved` - Plan approved
- `executing` - Applying patches
- `verifying` - Running tests
- `completed` - Done ✓
- `failed` - Failed ✗
- `cancelled` - Cancelled

## Monitoring

### Dashboard URLs
- **Codey**: http://localhost:8000/dashboard
- **Orty**: http://localhost:8080/

### Health Checks
```bash
# Orty health
curl http://localhost:8080/health

# Codey health
curl http://localhost:8000/health

# Backlog status
curl http://localhost:8080/v1/bug-reports \
  -H "X-Orty-Secret: OrtyIAmYourFather"

# Task status
curl http://localhost:8000/tasks
```

## Documentation

| Document | Purpose |
|----------|---------|
| `docs/BUG_REPORT_WORKFLOW.md` | End-to-end workflow |
| `docs/BACKLOG_MANAGEMENT.md` | Backlog processing |
| `docs/CLIENT_PROMOTION_SYSTEM.md` | Admin promotion |
| `docs/ORTY_CODEY_INTEGRATION.md` | Setup guide |
| `EVOLUTION_CHANGELOG.md` | Change log |
| `BUGFIX_SUMMARY_SUPERVISOR.md` | Supervisor role |

## Security Model

### Authentication
- **Admin secret**: `ORTY_SHARED_SECRET` (initial setup)
- **Client tokens**: Bearer tokens for API access
- **API keys**: Service-to-service (Orty ↔ Codey)

### Authorization
- **Admin clients**: Full access
- **Regular clients**: Limited to own resources
- **Promotion required**: Hash of admin secret proves knowledge

### Audit Trail
- All promotion requests recorded
- All bug status changes tracked
- All Codey task events logged

## Evolution Contract Compliance

### §1 User Precedence ✓
- User controls admin promotion
- High-risk bugs require user approval
- User can reject plans

### §2 Self-Evolution ✓
- Mode 0 (advisory) - changes proposed
- Atomic changes - one bug at a time
- Audit trail - all actions logged

### §3 Testing ✓
- Integration tests created
- Verification required for fixes
- Error handling implemented

### §4 Security ✓
- Secret hygiene (hash only)
- Least privilege (default: no admin)
- Network policy (configurable)

## Getting Started

```bash
# 1. Start Codey
cd /home/ortluk/ortluk-hub/Codey
./start_codey_server.sh

# 2. Start Orty
cd /home/ortluk/ortluk-hub/orty/Orty
source .venv/bin/activate
python -m uvicorn service.api:app --reload

# 3. Test integration
cd /home/ortluk/ortluk-hub/orty/Orty
./test_integration.sh

# 4. Process backlog (if any)
./scripts/process_backlog.sh pending
```

## Summary

This bug management system provides:

1. **Automated bug processing** - Alfred → Orty → Codey pipeline
2. **Supervised autonomy** - Orty auto-approves low-risk, requests approval for high-risk
3. **Client promotion** - Secure admin status delegation
4. **Backlog management** - Real-time or batch processing
5. **Full audit trail** - All actions logged and traceable
6. **Evolution contract compliance** - User control, safety, auditability

The system balances automation with user control, enabling efficient bug fixing while maintaining safety and transparency.
