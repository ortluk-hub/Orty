#!/usr/bin/env python3
"""Process Orty bug backlog with Codey using full lifecycle.

Usage: ./process_backlog.py [pending|all]
"""

import json
import os
import sys
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

# Add Orty src to path
ORTY_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ORTY_ROOT))

# Add Codey to path
sys.path.insert(0, os.path.expanduser('/home/ortluk/ortluk-hub/Codey/src'))

from cody.orty_integration import (
    BacklogProcessor,
    AutoApprovalConfig,
    BugReportScanner,
)

# Configuration
ORTY_URL = os.environ.get("ORTY_URL", "http://orty-server:8080")
CODEY_URL = os.environ.get("CODEY_URL", "http://orty-server:8000")
ORTY_SECRET = os.environ.get("ORTY_SECRET", "OrtyIAmYourFather")
CODEY_API_KEY = os.environ.get("CODEY_API_KEY", "orty-service-key")
ALFRED_WORKSPACE = os.environ.get("ALFRED_WORKSPACE", "/home/ortluk/ortluk-hub/Alfred/Alfred")
STATUS_FILTER = sys.argv[1] if len(sys.argv) > 1 else "pending"

print("============================================")
print("Bug Backlog Processor (Full Lifecycle)")
print("============================================")
print("")
print("Configuration:")
print(f"  Orty URL:       {ORTY_URL}")
print(f"  Codey URL:      {CODEY_URL}")
print(f"  Workspace:      {ALFRED_WORKSPACE}")
print(f"  Status filter:  {STATUS_FILTER}")
print("")

# Get bugs from Orty
print("Fetching bugs from Orty...")
try:
    req = Request(f"{ORTY_URL}/v1/bug-reports")
    req.add_header("X-Orty-Secret", ORTY_SECRET)
    with urlopen(req) as response:
        bugs = json.loads(response.read().decode())
except URLError as e:
    print(f"Error fetching bugs: {e}")
    sys.exit(1)

# Filter by status
if STATUS_FILTER == 'pending':
    filtered_bugs = [b for b in bugs if b.get('status') in ('pending', 'in_triage', 'in_codey_processing', None)]
elif STATUS_FILTER == 'all':
    filtered_bugs = bugs
else:
    filtered_bugs = [b for b in bugs if b.get('status') == STATUS_FILTER]

bug_count = len(filtered_bugs)
print(f"Found {bug_count} bugs to process")
print("")

if bug_count == 0:
    print("✓ Backlog is clean. Nothing to process.")
    sys.exit(0)

# Process each bug using full lifecycle
print("Processing backlog with full lifecycle...")
print("")

# Use Orty's bug report processor for lifecycle management
from service.integrations.bug_report_processor import BugReportProcessor
from service.integrations.codey_client import CodeyClient
from service.storage.db import SQLiteDB
from service.storage.bug_reports_repo import BugReportsRepository
from service.config import settings

# Initialize Orty components
db = SQLiteDB()
bug_reports_repo = BugReportsRepository(db)
codey_client = CodeyClient(base_url=CODEY_URL, api_key=CODEY_API_KEY)
bug_processor = BugReportProcessor(
    codey_client=codey_client,
    workspace_ref=ALFRED_WORKSPACE,
    bug_reports_repo=bug_reports_repo,
    auto_approve_low_risk=True,
    require_approval_for_high_risk=True,
)

successful = 0
failed = 0
results = []

for bug in filtered_bugs:
    print(f"Processing bug {bug['report_id'][:8]}...: {bug['title'][:50]}")

    result = bug_processor.process_bug_lifecycle(
        report_id=bug["report_id"],
        title=bug["title"],
        summary=bug["summary"],
        details=bug["details"],
        client_id=bug["client_id"],
        metadata=bug.get("metadata", {}),
    )

    if result and result.get("success"):
        successful += 1
        print(f"  ✓ Bug {bug['report_id'][:8]}... FIXED!")
    else:
        failed += 1
        print(f"  ✗ Bug {bug['report_id'][:8]}... FAILED or IN PROGRESS")

    results.append({
        "report_id": bug["report_id"][:8],
        "title": bug["title"][:50],
        "success": result.get("success") if result else False,
    })
    print("")

# Print summary
print("============================================")
print("Backlog Processing Summary")
print("============================================")
print(f"Total bugs:  {bug_count}")
print(f"Successful:  {successful}")
print(f"Failed:      {failed}")
print("")

if results:
    print("Individual Results:")
    print("--------------------------------------------")
    for r in results:
        status_icon = "✓" if r["success"] else "✗"
        print(f"  {status_icon} {r['report_id']}... {r['title']}")

print("")
print("============================================")

# Exit with error if any failed
if failed > 0:
    print(f"Warning: {failed} bugs failed or still in progress")
    sys.exit(1)

print("")
print("Backlog processing complete!")
