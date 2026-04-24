# Orty Conversational Bug Interface

## Overview

Orty now has full conversational access to the bug report system and Codey integration. You can chat about bugs naturally, and Orty will use the underlying tools like function calls.

## Conversation Examples

### List Bugs

**User:** "Show me all pending bugs"

**Orty:** [calls `GET /v1/bugs/list?status=pending`]

```
Here are your pending bugs:

1. **93c4c855** - "sometimes you crash when you're in offline mode"
   Status: planned | Codey: planned

2. **233b5110** - "navigation is broken even with full address"
   Status: planned | Codey: planned

3. **e215aa1d** - "not getting any voice hits"
   Status: planned | Codey: planned

Total: 3 pending bugs
```

### Get Bug Details

**User:** "What's the status of bug 93c4c855?"

**Orty:** [calls `GET /v1/bugs/93c4c855/status`]

```
Bug 93c4c855 "sometimes you crash when you're in offline mode":
- Orty status: planned
- Codey status: planned
- Codey task: e0734618

The bug has been analyzed by Codey and a fix plan is ready. Would you like me to approve it?
```

### Submit New Bug

**User:** "Report a bug - the keyboard has too much spacing above it"

**Orty:** [calls `POST /v1/bugs/submit?title=Keyboard%20spacing...`]

```
I've created bug report **abc12345** for the keyboard spacing issue.

Title: "Keyboard has excessive spacing above chat messages"
Status: pending

Should I forward this to Codey for analysis?
```

**User:** "Yes, send it to Codey"

**Orty:** [calls `POST /v1/bugs/abc12345/forward`]

```
Done! Bug abc12345 has been forwarded to Codey.

Codey task: def67890
Status: queued

Codey will analyze the issue and create a fix plan.
```

### Approve Fix Plan

**User:** "What bugs are ready for approval?"

**Orty:** [calls `GET /v1/bugs/list?status=planned`]

```
These bugs have fix plans ready for approval:

1. **93c4c855** - "sometimes you crash when you're in offline mode"
   Codey task: e0734618
   Confidence: 56% | Complexity: medium

2. **233b5110** - "navigation is broken even with full address"
   Codey task: ae97a4ce
   Confidence: 52% | Complexity: medium

Would you like me to approve any of these?
```

**User:** "Approve the fix for bug 93c4c855"

**Orty:** [calls `POST /v1/bugs/93c4c855/approve`]

```
✅ Plan approved for bug 93c4c855!

Codey task: e0734618
Status: plan_approved

Codey will now execute the fix on an isolated branch and run verification tests.
```

### Bug Statistics

**User:** "How many bugs do we have?"

**Orty:** [calls `GET /v1/bugs/stats/summary`]

```
Bug Report Summary:
- Total: 5 bugs
- Pending: 0
- Planned: 5 (awaiting approval)
- Fixed & Verified: 0

By Codey status:
- Planned: 5
- Completed: 0

Would you like me to process the backlog?
```

### Search Bugs

**User:** "Find bugs about crashes"

**Orty:** [calls `GET /v1/bugs/search?q=crashes`]

```
Found 2 bugs matching "crashes":

1. **93c4c855** - "sometimes you crash when you're in offline mode"
   Status: planned | Codey: planned

2. **8e385758** - "alfred crashed during the previous foreground session"
   Status: planned | Codey: planned
```

## API Reference

### Query Endpoints

| Endpoint | Description | Example |
|----------|-------------|---------|
| `GET /v1/bugs/list` | List bugs with filters | `?status=pending&limit=10` |
| `GET /v1/bugs/{id}` | Get full bug details | `/v1/bugs/93c4c855` |
| `GET /v1/bugs/{id}/status` | Get status only | `/v1/bugs/93c4c855/status` |
| `GET /v1/bugs/stats/summary` | Get statistics | - |
| `GET /v1/bugs/search` | Search bugs | `?q=crash&limit=20` |

### Action Endpoints

| Endpoint | Description | Example |
|----------|-------------|---------|
| `POST /v1/bugs/submit` | Create new bug | `?title=...&summary=...` |
| `POST /v1/bugs/{id}/forward` | Forward to Codey | `/v1/bugs/93c4c855/forward` |
| `POST /v1/bugs/{id}/approve` | Approve Codey plan | `/v1/bugs/93c4c855/approve` |
| `POST /v1/bugs/{id}/reject` | Reject Codey plan | `/v1/bugs/93c4c855/reject` |

## Tool Integration

### Using in Code

```python
from service.integrations.bug_report_tools import BugReportTools

# Get bug tools instance
bug_tools = BugReportTools(bug_reports_repo, codey_processor)

# List pending bugs
pending = bug_tools.list_bug_reports(status="pending")

# Get bug details
bug = bug_tools.get_bug_report("93c4c855")

# Submit new bug
new_bug = bug_tools.submit_bug_report(
    title="Keyboard spacing issue",
    summary="Too much space above keyboard",
    details="...",
    forward_to_codey=True,
)

# Approve Codey plan
result = bug_tools.approve_codey_plan("93c4c855")
```

### Conversation Flow

```
User Query
    ↓
Orty parses intent
    ↓
Calls appropriate tool method
    ↓
Formats response
    ↓
Presents to user with follow-up options
```

## Status States

### Orty Bug Status
- `pending` - New bug, not yet processed
- `in_codey_processing` - Submitted to Codey
- `planned` - Codey created fix plan
- `auto_approved_by_orty` - Orty auto-approved
- `waiting_user_approval` - Awaiting your approval
- `plan_approved` - Plan approved, executing
- `fixed_verified` - Complete ✓
- `fix_verification_failed` - Tests failed ✗

### Codey Task Status
- `queued` - Waiting to be processed
- `triaged` - Analysis complete
- `planned` - Fix plan created
- `plan_approved` - Plan approved
- `executing` - Applying patches
- `verifying` - Running tests
- `completed` - Done ✓
- `verification_failed` - Tests failed ✗

## Best Practices

### 1. Review Before Approving
Always check Codey's confidence and complexity before approving:
- **Confidence < 75%** → Manual review recommended
- **Complexity "medium" or "large"** → Consider impact

### 2. Use Descriptive Titles
When submitting bugs, include:
- What's broken
- Expected behavior
- Impact on users

### 3. Follow Up
After approving:
- Monitor task status
- Review generated diffs
- Test fixes before merging to production

## Example Conversation Flow

```
User: Show me pending bugs
Orty: [lists 3 bugs]

User: What's the status of the first one?
Orty: [shows details for 93c4c855]

User: What's Codey's plan?
Orty: [fetches and displays fix plan]

User: Looks good, approve it
Orty: [approves plan]
Orty: ✅ Approved! Codey is now executing the fix.

User: When will it be done?
Orty: [checks task status]
Orty: Codey is running verification tests. Should take ~2 minutes.

User: Notify me when it's complete
Orty: I'll monitor the task and let you know when verification passes.
```

## Future Enhancements

1. **Natural language approval** - "Yes, do it" → approve last discussed bug
2. **Batch operations** - "Approve all low-risk fixes"
3. **Automatic notifications** - "Tell me when bug 93c4c855 is fixed"
4. **PR creation** - "Create a PR for the approved fix"
5. **Integration with chat** - Inline bug status in conversations
