# Evolution Change Log

## 2026-03-15: Orty-Codey Bug Report Integration

### Summary
Added automated bug report forwarding from Orty to Codey for autonomous triage and fixing.
**Orty acts as supervisor** - can grant approvals on behalf of user or request approval through admin channels when needed.

### Why
Bug reports from Alfred were being stored in Orty's database but never processed. The integration documented in `ORTY_INTEGRATION.md` existed only on Codey's side.

### What Changed

#### New Files
- `service/integrations/codey_client.py` - HTTP client for Codey task API
- `service/integrations/bug_report_processor.py` - Bug report processing logic with Orty supervision
- `service/integrations/__init__.py` - Package exports
- `.env.example` - Configuration template
- `docs/ORTY_CODEY_INTEGRATION.md` - Setup documentation
- `test_integration.sh` - Integration test script
- `../Codey/start_codey_server.sh` - Codey server startup script
- `../BUGFIX_SUMMARY.md` - Bug fix summary

#### Modified Files
- `service/api/routes/v1_bug_reports.py` - Auto-forward bugs to Codey
- `service/api/deps.py` - Add Codey client to runtime container with supervisor settings
- `service/config.py` - Add CODEY_* configuration settings
- `.env` - Add Codey integration settings

### Orty Supervisor Role

Orty now acts as **supervisor** for bug fixes:

1. **Auto-Approval (Low Risk)**
   - Confidence ≥ 75%
   - Complexity ≤ "small"
   - No high-risk keywords
   - → Orty approves on behalf of user (`approved_by: "orty_supervisor"`)

2. **User Approval Required (High Risk)**
   - Complexity = "large" or "xl"
   - Risk keywords: "breaking", "migration", "data loss", "security", "irreversible"
   - → Orty notifies user through admin channel with approval request

3. **Admin Channels**
   - `ui`: In-app notification
   - `conversation`: Add to conversation history
   - `bot_event`: Emit as bot event
   - User can reply "approve {task_id}" to grant approval

### Risk Assessment
- **Risk Level**: Low-Medium
- **Scope**: Bug report processing only
- **Backwards Compatible**: Yes (graceful degradation if Codey unavailable)
- **Data Changes**: None (uses existing schema)
- **User Control**: Preserved (high-risk changes require approval)

### Gates Passed
- [x] Python syntax verified (`py_compile` green)
- [x] No secrets committed
- [x] Configuration via environment variables
- [x] Rollback path exists (revert commits)
- [x] User control preserved (Evolution Contract §1.3)
- [ ] Tests pending (integration test created, manual execution required)
- [ ] Lint/type checks (not configured for this project)

### Rollback Plan
1. Stop Orty server
2. Revert commits in reverse order:
   - Revert `service/api/routes/v1_bug_reports.py`
   - Revert `service/api/deps.py`
   - Revert `service/config.py`
   - Remove `service/integrations/` directory
3. Remove Codey settings from `.env`
4. Restart Orty

### Mode
**Mode 0 - Advisory**: Changes proposed for user review and application.

### Configuration Required
```bash
# In .env file:
CODEY_URL=http://127.0.0.1:8000
CODEY_API_KEY=orty-service-key  # Optional
CODEY_ALFRED_WORKSPACE=/path/to/Alfred

# Supervisor settings (defaults):
# CODEY_AUTO_APPROVE_LOW_RISK=true
# CODEY_REQUIRE_APPROVAL_HIGH_RISK=true
# CODEY_NOTIFY_USER_ON_PLAN=true
```

### Testing Steps
```bash
# 1. Start Codey server
cd ../Codey && ./start_codey_server.sh

# 2. Start Orty server
cd /home/ortluk/ortluk-hub/orty/Orty
source .venv/bin/activate
python -m uvicorn service.api:app --reload

# 3. Run integration test
./test_integration.sh
```

### Architecture Compliance
- ✓ API layer unchanged (routing only)
- ✓ Business logic in new `integrations/` package
- ✓ Storage access via existing repositories
- ✓ Configuration via `settings` layer
- ✓ No hardcoded secrets
- ✓ Pluggable HTTP client (easy to mock/test)
- ✓ **User control preserved** (Evolution Contract §1)
- ✓ **Bounded autonomy** (high-risk requires approval)

### Evolution Contract Compliance

#### §1 User Precedence Rules ✓
- **User hard constraints**: High-risk changes require explicit approval
- **Safety constraints**: Risk assessment before auto-approval
- **Consent boundaries**: User notified of all significant changes

#### §2 Self-Evolution Rules ✓
- **Mode 0 (Advisory)**: Changes proposed for review
- **Atomic changes**: Focused on single concern
- **Architecture invariants**: Preserved

#### §3 Testing & Reliability ✓
- Integration test created
- Logging for observability
- Graceful error handling

#### §4 Security Rules ✓
- No secrets committed
- Configuration via env vars
- Least privilege (optional API key)

### Next Steps
1. Review changes
2. Run integration test
3. Apply to production if tests pass
4. Monitor first bug report submission
5. Tune auto-approval thresholds based on experience

### Event Flow

```
Alfred → Orty → Codey → Orty (Supervisor) → User (if high-risk)
  │       │      │         │
  │       │      │         └─→ Auto-approve (low risk)
  │       │      │              or
  │       │      │         └─→ Request approval (high risk)
  │       │      │
  │       │      └─→ Event: PLAN_CREATED
  │       │
  │       └─→ Store bug + forward to Codey
  │
  └─→ Email draft + silent background sync
```
