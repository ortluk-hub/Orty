# ⚠️ AGENT READ ME FIRST ⚠️

## STOP - READ THIS BEFORE TOUCHING ANY CODE

**IF YOU ARE AN AGENT (Codey, Codex, Qwen, or any AI assistant):**

You MUST read and understand this document BEFORE analyzing or modifying any code in the Orty ecosystem.

**NO EXCEPTIONS.**

---

## PRIME DIRECTIVE

**ANY AGENT THAT TOUCHES CODE IN THIS ECOSYSTEM MUST:**

1. **FULLY UNDERSTAND ALL PARTS** before making changes
2. **TRACE COMPLETE CONTEXT** - even if it's 1 million lines
3. **FOLLOW THE EVOLUTION CONTRACT** - non-negotiable
4. **NO SHORTCUTS, NO GUESSES, NO VAGUE ANALYSIS**

---

## THE EVOLUTION CONTRACT

Reference: `/home/ortluk/ortluk-hub/orty/Orty/EvolutionContract.md`

### §1 User Precedence
- User instructions > Your preferences
- User constraints MUST be enforced (e.g., "local only", "no cloud")
- Stop/pause honored immediately

### §2 Self-Evolution
- Mode 0 (Advisory) is DEFAULT - propose, don't apply
- Atomic changes only - one logical change at a time
- No "rewrite everything" PRs

### §3 Testing
- Tests MUST pass before merge
- New features require tests
- Reproducibility required

### §4 Security
- NO secrets committed (API keys, tokens, credentials)
- Least privilege
- Network policy enforced

### §5 Audit
- All changes traceable via git
- Rollback plan required
- Change ledger maintained

**VIOLATION = REJECTED**

---

## COMPLETE ANALYSIS REQUIREMENT

**BEFORE proposing ANY code change:**

```
1. Trace FULL context
2. Understand ALL affected parts
3. Identify root cause with PROOF
4. No changes without complete analysis
```

### If Confidence < 75%

You MUST generate an **EXPLICIT TRACING PLAN**:

```markdown
## Tracing Plan

| Step | Action | Target | Files | Why | Looking For |
|------|--------|--------|-------|-----|-------------|
| 1 | trace_subsystem | local_llm_runtime | llm.py, runtime.py | Keywords: crash, offline | Code paths for offline mode |
| 2 | trace_entry_points | user actions | [files] | Bug triggered by... | Call chain from entry to failure |
| 3 | search_error_patterns | crash | [files] | Error handling code | Exception throws, logging |
| 4 | check_recent_changes | git_log | [commits] | Recent changes | Commits that introduced bug |
| 5 | check_related_tests | test_files | [tests] | Tests for functionality | Failing tests confirming bug |
```

**NO TRACING PLAN = NO CHANGES ALLOWED**

### If Tracing Required

You MUST execute ALL steps before proposing fixes:

```
Steps executed: 3/10
Status: INCOMPLETE
Changes Allowed: NO ❌

Steps executed: 10/10
Status: COMPLETE
Changes Allowed: YES ✓
```

---

## SLICED PROJECT PLAN FORMAT

All work follows sliced plans. Reference: `/home/ortluk/ortluk-hub/Codey/Projectplan.md`

### Current Snapshot

Check the project plan for:
- Current slice number
- Slice status (Green/Yellow/Red)
- Last green slice
- Active blockers
- Next operator checkpoint

### Before Starting Work

1. **Read current slice plan** - understand goal, build, tests, exit criteria
2. **Check slice gates** - tests must be green
3. **Check checkpoints** - operator approval may be required
4. **Stay in scope** - don't work outside current slice

### Slice Gates

```
Slice N is NOT clear until:
□ Tests green
□ Goal achieved
□ Exit criteria met
□ Operator checkpoint cleared (if required)
```

---

## WORKFLOW

### For Bug Fixes

```
1. Receive bug report
   ↓
2. Triage (analyze)
   ↓
3. IF confidence < 75%:
   → Generate EXPLICIT tracing plan
   → Execute ALL tracing steps
   → Identify root cause with PROOF
   ↓
4. Create fix plan (with contract compliance)
   ↓
5. Submit for approval (Mode 0 default)
   ↓
6. If approved → Execute on isolated branch
   ↓
7. Run tests (MUST pass)
   ↓
8. Verify (MUST succeed)
   ↓
9. Complete - PR ready for review
```

### For Features/Tasks

```
1. Receive task (feature_request, planning_task, etc.)
   ↓
2. Check Evolution Contract compliance
   ↓
3. Check slice plan alignment
   ↓
4. Inspect workspace (REQUIRED)
   ↓
5. Analyze requirements
   ↓
6. Create plan (with compliance check)
   ↓
7. Submit for approval
   ↓
8. If approved → Execute
   ↓
9. Test → Verify → Complete
```

---

## CONTRACT COMPLIANCE CHECK

Before ANY change, verify:

```python
from cody.evolution_contract import check_task_compliance

compliance = check_task_compliance(
    task_type="bug_report",  # or feature_request, etc.
    task_payload={
        "requirements": [...],
        "constraints": [...],
        "triage_artifact": {...},
        "workspace_inspected": True,  # MUST be True
    },
    proposed_changes={...},
)

if not compliance.compliant:
    # BLOCKED - cannot proceed
    print(f"❌ Contract violations: {compliance.violations}")
    print(f"Warnings: {compliance.warnings}")
    return

# Compliance passed - can proceed
print(f"✓ Contract compliant: {compliance.gates_passed}")
```

### Common Violations

| Violation | Cause | Fix |
|-----------|-------|-----|
| `INCOMPLETE_ANALYSIS` | Tracing plan missing or incomplete | Generate and execute full tracing plan |
| `USER_CONSTRAINT` | Violated user constraint | Respect constraint
| `TESTING` | Tests not passing | Fix tests before proposing changes |
| `SECURITY` | Potential secret detected | Remove secrets, use env vars |
| `SLICE_PLAN` | Outside slice scope or gates not green | Align with slice, pass gates |

---

## COMMUNICATION

### When Presenting Analysis

```markdown
## Bug Analysis

**Confidence:** 50% (LOW)

**Status:** ⚠️ INCOMPLETE - Tracing Required

**Tracing Plan:**
| Step | Action | Target | Status |
|------|--------|--------|--------|
| 1 | trace_subsystem | local_llm_runtime | ✓ Complete |
| 2 | trace_entry_points | user actions | ✓ Complete |
| 3 | search_error_patterns | crash | 🔄 In Progress |
| 4 | check_recent_changes | git_log | ⏳ Pending |
| 5 | check_related_tests | test_files | ⏳ Pending |

**Progress:** 2/5 steps (40%)

**Changes Allowed:** NO ❌

**Next Step:** Complete step 3 (search error patterns)
```

### When Proposing Changes

```markdown
## Fix Proposal

**Root Cause:** `offline_handler.py:347` - Race condition between network state and LLM queue

**Evidence:**
- ✓ Full call graph traced (entry → failure)
- ✓ All affected files identified (5 files)
- ✓ Recent commit that introduced bug (abc123)
- ✓ Minimal reproduction case created

**Contract Compliance:** ✓ PASSED
- Full context understood: YES
- Tracing complete: YES (5/5 steps)
- Root cause proven: YES
- Tests passing: YES
- No secrets: YES
- Rollback plan: YES (revert commit)

**Proposed Changes:**
```diff
--- a/src/offline_handler.py
+++ b/src/offline_handler.py
@@ -344,7 +344,9 @@ class OfflineHandler:
         self.queue = []
         self.network_state = NetworkState.UNKNOWN
-        self.processing = False
+        self.processing = False
+        self.lock = threading.Lock()  # NEW: Synchronization
```

**Tests Added:**
- `test_offline_race_condition.py` - Reproduces and verifies fix

**Rollback Plan:** Revert commit abc123
```

---

## FORBIDDEN ACTIONS

**NEVER:**

❌ Propose changes without complete analysis
❌ Skip tracing steps
❌ Guess at root causes
❌ Commit secrets or credentials
❌ Modify files outside workspace boundary
❌ Bypass tests
❌ Auto-merge without approval (Mode 0 default)
❌ Work outside slice scope
❌ Advance with yellow/red gates

---

## REQUIRED ACTIONS

**ALWAYS:**

✓ Read this document first
✓ Read Evolution Contract
✓ Read current slice plan
✓ Trace full context (even if 1M lines)
✓ Generate tracing plan for low-confidence bugs
✓ Execute ALL tracing steps
✓ Identify root cause with PROOF
✓ Check contract compliance
✓ Pass all gates before merge
✓ Provide rollback plan

---

## QUICK REFERENCE

### Key Documents

| Document | Path |
|----------|------|
| Evolution Contract | `/home/ortluk/ortluk-hub/orty/Orty/EvolutionContract.md` |
| Sliced Plan Format | `/home/ortluk/ortluk-hub/Codey/docs/SLICED_PROJECT_PLAN_FORMAT.md` |
| Complete Analysis | `/home/ortluk/ortluk-hub/Codey/docs/COMPLETE_ANALYSIS_REQUIREMENT.md` |
| Explicit Tracing | `/home/ortluk/ortluk-hub/Codey/docs/EXPLICIT_TRACING_PLANS.md` |
| Contract Enforcement | `/home/ortluk/ortluk-hub/Codey/docs/EVOLUTION_CONTRACT_ENFORCEMENT.md` |

### Key Commands

```bash
# Check contract compliance
python3 -c "from cody.evolution_contract import check_task_compliance; ..."

# Run tests
pytest -q

# Check slice status
cat /home/ortluk/ortluk-hub/Codey/Projectplan.md | grep -A 10 "Current Snapshot"

# Check git status
git status

# Check for secrets in diff
git diff --check
```

---

## ACKNOWLEDGMENT

**BEFORE starting work, confirm:**

```
[✓] I have read this AGENTS README
[✓] I have read the Evolution Contract
[✓] I have read the current slice plan
[✓] I understand the complete analysis requirement
[✓] I understand the tracing plan requirement
[✓] I will not propose changes without full context
[✓] I will check contract compliance before changes
[✓] I will pass all gates before merge
```

**IF YOU CANNOT CHECK ALL BOXES: STOP AND READ THE REQUIRED DOCUMENTS**

---

## ENFORCEMENT

**This document is ENFORCED by:**

1. `cody.evolution_contract` module - automated compliance checks
2. Slice gates - tests must be green
3. Operator checkpoints - human review required
4. Git hooks - prevent secrets, enforce gates

**VIOLATIONS = BLOCKED + LOGGED**

---

## QUESTIONS?

If unsure about ANY requirement:

1. Re-read this document
2. Re-read Evolution Contract
3. Ask for clarification

**DO NOT PROCEED UNTIL CERTAIN**

---

**REMEMBER:**

```
┌─────────────────────────────────────────┐
│  UNDERSTAND FIRST, CHANGE SECOND        │
├─────────────────────────────────────────┤
│  If it takes 1 line → trace 1 line      │
│  If it takes 1M lines → trace 1M lines  │
│                                         │
│  NO EXCEPTIONS                          │
└─────────────────────────────────────────┘
```

**NOW YOU MAY PROCEED** ✓
