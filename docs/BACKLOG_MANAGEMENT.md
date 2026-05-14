# Bug Backlog Management

## Overview

The bug backlog is managed through a coordinated workflow between Orty (storage + supervision) and Codey (processing). Bugs can be processed individually as they arrive or in batches as a backlog.

## Backlog Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        BUG BACKLOG FLOW                                  │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────┐
│   Alfred    │  (Multiple bug reports over time)
└──────┬──────┘
       │
       │ Individual submissions
       │ POST /v1/bug-reports
       │
       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Orty Bug Reports Table (SQLite)                                        │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │ report_id | title | status | codey_task_id | created_at | ... │    │
│  ├────────────────────────────────────────────────────────────────┤    │
│  │ uuid-001  | Wake word... | fixed_verified | task-123 | ...   │    │
│  │ uuid-002  | Battery...   | pending         | NULL     | ...   │    │
│  │ uuid-003  | UI glitch... | in_codey_processing | task-456 | ...│    │
│  │ uuid-004  | Crash on...  | waiting_user_approval | task-789 | │    │
│  │ uuid-005  | Memory leak  | pending         | NULL     | ...   │    │
│  │ ...        | ...          | ...             | ...      | ...   │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                          │
│                          │ Backlog = All bugs with status = "pending"
│                          │       + bugs stuck in processing
└──────────────────────────┼─────────────────────────────────────────────┘
                           │
                           │ Batch Processing Options:
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│  Manual       │  │  Scheduled    │  │  Event-       │
│  Trigger      │  │  Job          │  │  Driven       │
│               │  │               │  │               │
│ Admin runs:   │  │ Cron job:     │  │ Threshold:    │
│ ./process_    │  │ Every night   │  │ When 10+ bugs │
│ backlog.sh    │  │ at 2 AM       │  │ pending       │
└───────┬───────┘  └───────┬───────┘  └───────┬───────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  BacklogProcessor (Codey)                                               │
│                                                                         │
│  1. Scan Orty bug_reports table                                        │
│  2. Filter to pending bugs                                             │
│  3. Sort by priority (critical > high > normal > low)                  │
│  4. For each bug:                                                      │
│     a. Submit to Codey as task                                         │
│     b. Track to triage                                                 │
│     c. Auto-approve if eligible                                        │
│     d. Track to completion (or wait for user approval)                 │
│  5. Generate summary report                                            │
└─────────────────────────────────────────────────────────────────────────┘
                           │
                           │ POST /tasks (for each bug)
                           │
                           ▼
┌─────────────┐
│    Codey    │  (Multiple tasks processing in parallel)
└─────────────┘
```

## Backlog Processing Modes

### 1. Real-Time Processing (Default)

Bugs are processed individually as they arrive:

```python
# In Orty's bug report route
@router.post("/v1/bug-reports")
async def create_bug_report(payload: ...):
    # 1. Store bug
    record = runtime.bug_reports_repo.create_report(...)

    # 2. Forward to Codey immediately
    if runtime.codey_bug_processor:
        codey_task = runtime.codey_bug_processor.submit_to_codey(...)

    return record
```

**Pros:**
- Immediate feedback to user
- No backlog accumulation
- Easy to track individual bugs

**Cons:**
- May overwhelm Codey during bug storms
- No prioritization across bugs
- Less efficient resource usage

### 2. Batch Processing (Scheduled)

Bugs are processed in batches at scheduled times:

```python
# Scheduled job (e.g., cron, Celery beat)
from cody.orty_integration import BacklogProcessor, AutoApprovalConfig

async def process_bug_backlog():
    # 1. Get pending bugs from Orty
    pending_bugs = get_pending_bugs_from_orty()

    # 2. Configure processing
    config = AutoApprovalConfig(
        auto_approve_confidence_threshold=0.75,
        auto_approve_max_risk="low",
        auto_approve_max_complexity="small",
        auto_approve_products=["alfred"],
    )

    # 3. Process backlog
    processor = BacklogProcessor(
        codey_url="http://codey:8000",
        api_key="orty-service-key",
        auto_approval_config=config,
        workspace_ref="/path/to/Alfred",
    )

    summary = processor.process_backlog(
        bug_reports=pending_bugs,
        auto_approve=True,
    )

    # 4. Log results
    logger.info(f"Processed {summary.total_bugs} bugs")
    logger.info(f"  Completed: {summary.completed}")
    logger.info(f"  Auto-approved: {summary.auto_approved}")
    logger.info(f"  Manual review: {summary.manual_review_required}")

    return summary
```

**Pros:**
- Efficient resource usage
- Can prioritize across bugs
- Better for high-volume scenarios

**Cons:**
- Delayed feedback to users
- Bugs may sit pending for hours
- Requires scheduling infrastructure

### 3. Event-Driven Processing

Bugs are processed when thresholds are met:

```python
# Triggered when pending bugs > threshold
async def on_backlog_threshold_reached():
    if get_pending_bug_count() >= 10:
        await process_bug_backlog()
```

**Pros:**
- Balances immediacy and efficiency
- Prevents backlog accumulation
- Adaptive to load

**Cons:**
- More complex to implement
- Requires monitoring infrastructure

## Backlog Prioritization

### Priority Levels

```python
class BugPriority(Enum):
    CRITICAL = "critical"    # System down, data loss
    HIGH = "high"           # Major feature broken
    NORMAL = "normal"       # Standard bugs
    LOW = "low"             # Cosmetic, minor issues
```

### Priority Queue Processing

```python
def prioritize_backlog(bugs: list[BugReport]) -> list[BugReport]:
    """Sort bugs by priority and age."""

    priority_order = {
        BugPriority.CRITICAL: 0,
        BugPriority.HIGH: 1,
        BugPriority.NORMAL: 2,
        BugPriority.LOW: 3,
    }

    return sorted(
        bugs,
        key=lambda bug: (
            priority_order.get(bug.priority, 2),  # Priority first
            -bug.reported_at,                      # Then age (newer first)
        ),
    )
```

### Auto-Approval by Priority

```python
# High-priority bugs may have different auto-approval rules
AUTO_APPROVAL_BY_PRIORITY = {
    BugPriority.CRITICAL: {
        "confidence_threshold": 0.60,  # Lower threshold for speed
        "max_complexity": "medium",     # Allow more complex fixes
        "max_risk": "medium",           # Accept more risk
    },
    BugPriority.HIGH: {
        "confidence_threshold": 0.70,
        "max_complexity": "small",
        "max_risk": "low",
    },
    BugPriority.NORMAL: {
        "confidence_threshold": 0.75,
        "max_complexity": "small",
        "max_risk": "low",
    },
    BugPriority.LOW: {
        "confidence_threshold": 0.80,
        "max_complexity": "trivial",
        "max_risk": "low",
    },
}
```

## Backlog Status Tracking

### Bug Status States

```
┌─────────────────────────────────────────────────────────────────────┐
│                      BUG BACKLOG STATES                              │
└─────────────────────────────────────────────────────────────────────┘

pending                    # New bug, not yet processed
  │
  ├─→ in_codey_processing  # Submitted to Codey
  │     │
  │     ├─→ triaged        # Codey analyzed
  │     │     │
  │     │     ├─→ planned  # Fix plan created
  │     │     │     │
  │     │     │     ├─→ auto_approved_by_orty
  │     │     │     ├─→ waiting_user_approval
  │     │     │     │     │
  │     │     │     │     └─→ plan_approved
  │     │     │     │
  │     │     │     └─→ plan_rejected
  │     │     │
  │     │     └─→ cannot_reproduce
  │     │
  │     └─→ codey_error    # Codey processing failed
  │
  ├─→ fixed_verified       # Complete ✓
  ├─→ fix_verification_failed
  ├─→ wont_fix
  └─→ duplicate
```

### Querying Backlog Status

```sql
-- Get backlog summary
SELECT
    status,
    COUNT(*) as count,
    MIN(created_at) as oldest,
    MAX(created_at) as newest
FROM bug_reports
WHERE source = 'alfred-bug-report'
GROUP BY status;

-- Get bugs awaiting user approval
SELECT * FROM bug_reports
WHERE status = 'waiting_user_approval'
ORDER BY created_at DESC;

-- Get stuck bugs (in processing > 1 hour)
SELECT * FROM bug_reports
WHERE status IN ('in_codey_processing', 'triaged', 'planned')
  AND updated_at < datetime('now', '-1 hour');

-- Get completion rate
SELECT
    COUNT(*) as total,
    SUM(CASE WHEN status = 'fixed_verified' THEN 1 ELSE 0 END) as fixed,
    ROUND(100.0 * SUM(CASE WHEN status = 'fixed_verified' THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate
FROM bug_reports
WHERE source = 'alfred-bug-report';
```

## Backlog Processing Script

```bash
#!/usr/bin/env bash
# process_backlog.sh - Process Orty bug backlog

set -e

ORTY_URL="${ORTY_URL:-http://127.0.0.1:8080}"
CODEY_URL="${CODEY_URL:-http://127.0.0.1:8000}"
ORTY_SECRET="${ORTY_SECRET:-OrtyIAmYourFather}"
CODEY_API_KEY="${CODEY_API_KEY:-orty-service-key}"
ALFRED_WORKSPACE="${ALFRED_WORKSPACE:-/home/ortluk/ortluk-hub/Alfred/Alfred}"

echo "============================================"
echo "Bug Backlog Processor"
echo "============================================"
echo ""

# Get pending bugs from Orty
echo "Fetching pending bugs from Orty..."
PENDING_BUGS=$(curl -s "${ORTY_URL}/v1/bug-reports" \
    -H "X-Orty-Secret: ${ORTY_SECRET}" | \
    python3 -c "
import sys, json
bugs = json.load(sys.stdin)
pending = [b for b in bugs if b.get('status') in ('pending', 'in_codey_processing')]
print(json.dumps(pending))
")

BUG_COUNT=$(echo "$PENDING_BUGS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")

echo "Found ${BUG_COUNT} pending bugs"

if [ "$BUG_COUNT" -eq 0 ]; then
    echo "Backlog is clean. Nothing to process."
    exit 0
fi

# Process backlog with Codey
echo ""
echo "Processing backlog with Codey..."
python3 << PYTHON_SCRIPT
import json
import sys
sys.path.insert(0, '/home/ortluk/ortluk-hub/Codey/src')

from cody.orty_integration import (
    BacklogProcessor,
    AutoApprovalConfig,
    BugReport,
    BugPriority,
    BugStatus,
    BugReportScanner,
)

# Parse pending bugs from Orty
pending_bugs_json = '''${PENDING_BUGS}'''
pending_bugs = json.loads(pending_bugs_json)

# Convert to BugReport objects
scanner = BugReportScanner()
bug_reports = scanner.scan_from_table([
    {
        "bug_id": b["report_id"],
        "title": b["title"],
        "description": b["summary"] + "\\n\\n" + b["details"],
        "source_product": "alfred",
        "priority": "normal",  # Could infer from content
        "status": "new",
        "reported_at": b.get("createdAt", 0),
        "metadata": b.get("metadata", {}),
    }
    for b in pending_bugs
])

# Configure auto-approval
config = AutoApprovalConfig(
    auto_approve_confidence_threshold=0.75,
    auto_approve_max_risk="low",
    auto_approve_max_complexity="small",
    auto_approve_products=["alfred"],
)

# Process backlog
processor = BacklogProcessor(
    codey_url="${CODEY_URL}",
    api_key="${CODEY_API_KEY}",
    auto_approval_config=config,
    workspace_ref="${ALFRED_WORKSPACE}",
)

summary = processor.process_backlog(
    bug_reports=bug_reports,
    auto_approve=True,
)

# Print results
print("")
print("============================================")
print("Backlog Processing Summary")
print("============================================")
print(f"Total bugs:     {summary.total_bugs}")
print(f"Successful:     {summary.successful}")
print(f"Failed:         {summary.failed}")
print(f"Auto-approved:  {summary.auto_approved}")
print(f"Manual review:  {summary.manual_review_required}")
print(f"Completed:      {summary.completed}")
print(f"In progress:    {summary.in_progress}")
print(f"Queued:         {summary.queued}")
print(f"Processing time: {summary.processing_time_ms}ms")
print("")

# Print individual results
if summary.results:
    print("Individual Results:")
    for result in summary.results:
        status_icon = "✓" if result.success else "✗"
        auto_icon = "🤖" if result.was_auto_approved else ""
        print(f"  {status_icon} {result.bug_id}: {result.codey_task_status or result.error} {auto_icon}")

PYTHON_SCRIPT

echo ""
echo "Backlog processing complete!"
```

## Monitoring & Alerts

### Backlog Health Metrics

```python
# Monitor backlog health
def get_backlog_metrics() -> dict:
    """Get backlog health metrics."""

    return {
        "total_pending": count_bugs_by_status("pending"),
        "total_in_progress": count_bugs_by_status("in_codey_processing"),
        "total_waiting_approval": count_bugs_by_status("waiting_user_approval"),
        "oldest_pending_age_hours": get_oldest_bug_age("pending"),
        "completion_rate_24h": get_completion_rate(hours=24),
        "avg_processing_time_minutes": get_avg_processing_time(),
        "auto_approval_rate": get_auto_approval_rate(),
    }

# Alert thresholds
ALERT_THRESHOLDS = {
    "max_pending_bugs": 20,
    "max_in_progress_bugs": 10,
    "max_waiting_approval_hours": 24,
    "min_completion_rate": 0.80,
    "max_avg_processing_time_minutes": 30,
}

# Check and alert
def check_backlog_health():
    metrics = get_backlog_metrics()

    alerts = []

    if metrics["total_pending"] > ALERT_THRESHOLDS["max_pending_bugs"]:
        alerts.append(f"High pending backlog: {metrics['total_pending']} bugs")

    if metrics["oldest_pending_age_hours"] > ALERT_THRESHOLDS["max_waiting_approval_hours"]:
        alerts.append(f"Old pending bug: {metrics['oldest_pending_age_hours']} hours")

    if metrics["completion_rate_24h"] < ALERT_THRESHOLDS["min_completion_rate"]:
        alerts.append(f"Low completion rate: {metrics['completion_rate_24h']:.0%}")

    if alerts:
        send_alert("\n".join(alerts))
```

### Dashboard View

```sql
-- Backlog dashboard query
SELECT
    DATE(created_at) as date,
    COUNT(*) as new_bugs,
    SUM(CASE WHEN status = 'fixed_verified' THEN 1 ELSE 0 END) as fixed_bugs,
    SUM(CASE WHEN status LIKE '%failed%' THEN 1 ELSE 0 END) as failed_bugs,
    ROUND(100.0 * SUM(CASE WHEN status = 'fixed_verified' THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate
FROM bug_reports
WHERE created_at > datetime('now', '-30 days')
GROUP BY DATE(created_at)
ORDER BY date DESC;
```

## Evolution Contract Compliance

### §1 User Precedence Rules ✓
- User can configure auto-approval thresholds
- High-risk bugs require user approval
- User can review backlog before processing

### §2 Self-Evolution Rules ✓
- Backlog processing is auditable (all actions logged)
- Changes are atomic (one bug at a time)
- Rollback possible (reject plans, revert patches)

### §3 Testing & Reliability ✓
- Backlog processor has error handling
- Failed bugs don't block others
- Progress is tracked and reported

### §4 Security Rules ✓
- Authentication required (API keys)
- Least privilege (only process pending bugs)
- Audit trail (all actions logged)

## Files & Components

### Codey (Backlog Processing)
- `src/cody/orty_integration.py`
  - `BugReportScanner` - Scan Orty bug table
  - `BacklogProcessor` - Process backlog
  - `AutoApprovalEngine` - Approval rules
  - `CodeyTaskManager` - Task lifecycle

### Orty (Storage + Supervision)
- `service/storage/bug_reports_repo.py` - Bug storage
- `service/integrations/bug_report_processor.py` - Forward to Codey
- `service/api/routes/v1_bug_reports.py` - API endpoints

### Scripts
- `orty/Orty/scripts/process_backlog.sh` - Manual trigger
- `orty/Orty/scripts/check_backlog_health.py` - Monitoring

## Configuration

```bash
# Backlog processing settings
BACKLOG_PROCESSING_MODE="real_time"  # real_time, batch, event_driven
BACKLOG_BATCH_SIZE=10                # Max bugs per batch
BACKLOG_PROCESSING_SCHEDULE="0 2 * * *"  # Cron: daily at 2 AM
BACKLOG_THRESHOLD=10                 # Event-driven: process when > 10 pending

# Auto-approval settings
AUTO_APPROVE_CONFIDENCE_THRESHOLD=0.75
AUTO_APPROVE_MAX_RISK="low"
AUTO_APPROVE_MAX_COMPLEXITY="small"
AUTO_APPROVE_PRODUCTS="alfred,orty"

# Alert settings
ALERT_MAX_PENDING_BUGS=20
ALERT_MAX_AGE_HOURS=24
ALERT_MIN_COMPLETION_RATE=0.80
```

## Next Steps

1. **Implement batch processing scheduler** (Celery, cron)
2. **Add backlog dashboard** to Orty web UI
3. **Implement priority inference** from bug content
4. **Add alerting** (Slack, email)
5. **Create backlog health report** (weekly summary)
6. **Implement retry logic** for failed bugs
