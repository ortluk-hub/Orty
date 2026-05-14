#!/usr/bin/env bash
# Test Orty-Codey integration
# Usage: ./test_integration.sh

set -e

ORTY_URL="${ORTY_URL:-http://127.0.0.1:8080}"
CODEY_URL="${CODEY_URL:-http://127.0.0.1:8000}"
ORTY_SECRET="${ORTY_SECRET:-OrtyIAmYourFather}"

echo "============================================"
echo "Orty-Codey Integration Test"
echo "============================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass() {
    echo -e "${GREEN}✓${NC} $1"
}

fail() {
    echo -e "${RED}✗${NC} $1"
    exit 1
}

info() {
    echo -e "${YELLOW}→${NC} $1"
}

# Test 1: Check Codey is running
info "Test 1: Checking if Codey is running..."
if curl -s --connect-timeout 5 "${CODEY_URL}/health" > /dev/null; then
    pass "Codey is running at ${CODEY_URL}"
else
    fail "Codey is not running at ${CODEY_URL}"
fi

# Test 2: Check Orty is running
info "Test 2: Checking if Orty is running..."
if curl -s --connect-timeout 5 "${ORTY_URL}/health" > /dev/null; then
    pass "Orty is running at ${ORTY_URL}"
else
    fail "Orty is not running at ${ORTY_URL}"
fi

# Test 3: Submit a test bug report to Orty
info "Test 3: Submitting test bug report to Orty..."
RESPONSE=$(curl -s -X POST "${ORTY_URL}/v1/bug-reports" \
    -H "Content-Type: application/json" \
    -H "X-Orty-Secret: ${ORTY_SECRET}" \
    -d '{
        "client": "test-client",
        "title": "Integration Test Bug",
        "summary": "Testing Orty-Codey integration",
        "details": "This is a test bug report to verify the integration works correctly.",
        "metadata": {
            "test": "true",
            "source": "integration_test"
        }
    }')

REPORT_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('report_id', ''))" 2>/dev/null || echo "")

if [ -n "$REPORT_ID" ]; then
    pass "Bug report created with ID: ${REPORT_ID}"
else
    fail "Failed to create bug report. Response: ${RESPONSE}"
fi

# Test 4: Verify bug report was stored in Orty
info "Test 4: Verifying bug report in Orty..."
BUG_REPORTS=$(curl -s "${ORTY_URL}/v1/bug-reports" \
    -H "X-Orty-Secret: ${ORTY_SECRET}")

REPORT_COUNT=$(echo "$BUG_REPORTS" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

if [ "$REPORT_COUNT" -gt 0 ]; then
    pass "Found ${REPORT_COUNT} bug report(s) in Orty"
else
    fail "No bug reports found in Orty"
fi

# Test 5: Check if Codey received the task
info "Test 5: Checking if Codey received the task..."
sleep 2  # Give Codey time to process

TASKS=$(curl -s "${CODEY_URL}/tasks")
TASK_COUNT=$(echo "$TASKS" | python3 -c "import sys, json; data = json.load(sys.stdin); print(len(data) if isinstance(data, list) else 0)" 2>/dev/null || echo "0")

if [ "$TASK_COUNT" -gt 0 ]; then
    pass "Found ${TASK_COUNT} task(s) in Codey"

    # Find the task for our bug report
    TASK_ID=$(echo "$TASKS" | python3 -c "
import sys, json
tasks = json.load(sys.stdin)
for task in tasks:
    if task.get('title') == 'Integration Test Bug':
        print(task.get('task_id', ''))
        break
" 2>/dev/null || echo "")

    if [ -n "$TASK_ID" ]; then
        pass "Found matching task with ID: ${TASK_ID}"

        # Get task details
        info "Task Details:"
        TASK_DETAILS=$(curl -s "${CODEY_URL}/tasks/${TASK_ID}")
        echo "$TASK_DETAILS" | python3 -m json.tool 2>/dev/null || echo "$TASK_DETAILS"
    else
        info "No matching task found (may need manual triage)"
    fi
else
    info "No tasks found in Codey (integration may not be enabled)"
fi

# Test 6: List Codey dashboard
info "Test 6: Checking Codey dashboard..."
DASHBOARD=$(curl -s -o /dev/null -w "%{http_code}" "${CODEY_URL}/dashboard")
if [ "$DASHBOARD" = "200" ]; then
    pass "Codey dashboard is accessible at ${CODEY_URL}/dashboard"
else
    info "Codey dashboard returned status: ${DASHBOARD}"
fi

echo ""
echo "============================================"
echo "Integration Test Complete"
echo "============================================"
echo ""
echo "Summary:"
echo "  - Orty URL:  ${ORTY_URL}"
echo "  - Codey URL: ${CODEY_URL}"
echo "  - Bug Report ID: ${REPORT_ID}"
echo ""
echo "Next Steps:"
echo "  1. View Codey dashboard: ${CODEY_URL}/dashboard"
echo "  2. Manually triage task: curl -X POST ${CODEY_URL}/tasks/${TASK_ID}/triage"
echo "  3. View task events: curl ${CODEY_URL}/tasks/${TASK_ID}/events"
echo ""
