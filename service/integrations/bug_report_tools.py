"""Bug report and task tools for Orty.

This module provides conversational access to bug tracking and Codey integration.
"""

import logging
from typing import Any

from service.integrations.bug_report_processor import BugReportProcessor
from service.storage.bug_reports_repo import BugReportsRepository


logger = logging.getLogger(__name__)


class BugReportTools:
    """Conversational bug report tools for Orty.

    These methods can be called directly from conversation context,
    allowing Orty to chat about bugs and use them like tool calls.
    """

    def __init__(
        self,
        bug_reports_repo: BugReportsRepository,
        codey_processor: BugReportProcessor | None = None,
    ):
        self.bug_reports_repo = bug_reports_repo
        self.codey_processor = codey_processor

    # === Query Tools ===

    def list_bug_reports(
        self,
        status: str | None = None,
        source: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """List bug reports with optional filtering.

        Args:
            status: Filter by status (pending, planned, fixed_verified, etc.)
            source: Filter by source (alfred-bug-report, etc.)
            limit: Maximum number of bugs to return

        Returns:
            List of bug report summaries
        """
        logger.info(f"Listing bugs: status={status}, source={source}, limit={limit}")

        # Get all bugs (admin access)
        all_bugs = self.bug_reports_repo.list_reports(
            client_id=None,  # Admin can see all
            source=source,
            limit=limit * 2,  # Fetch extra for filtering
        )

        # Filter by status if specified
        if status:
            filtered_bugs = [
                b for b in all_bugs
                if b.get("status") == status or b.get("codey_status") == status
            ]
        else:
            filtered_bugs = all_bugs

        # Return formatted summaries
        return [
            {
                "report_id": b["report_id"][:8],
                "title": b["title"],
                "status": b.get("status", "unknown"),
                "codey_status": b.get("codey_status"),
                "codey_task_id": b.get("codey_task_id", "")[:8] if b.get("codey_task_id") else None,
                "client": b.get("client"),
                "created_at": b.get("created_at", ""),
            }
            for b in filtered_bugs[:limit]
        ]

    def get_bug_report(self, report_id: str) -> dict | None:
        """Get full details of a specific bug report.

        Args:
            report_id: Bug report ID (full or 8-char prefix)

        Returns:
            Full bug report details or None
        """
        # Try exact match first
        bug = self.bug_reports_repo.get_report(report_id)

        # Try prefix match if not found
        if not bug and len(report_id) == 8:
            all_bugs = self.bug_reports_repo.list_reports(client_id=None, limit=100)
            for b in all_bugs:
                if b["report_id"].startswith(report_id):
                    bug = b
                    break

        if not bug:
            return None

        # Return formatted details
        return {
            "report_id": bug["report_id"],
            "title": bug["title"],
            "summary": bug["summary"],
            "details": bug["details"][:500] + "..." if len(bug.get("details", "")) > 500 else bug.get("details", ""),
            "status": bug.get("status", "unknown"),
            "codey_status": bug.get("codey_status"),
            "codey_task_id": bug.get("codey_task_id"),
            "client": bug.get("client"),
            "client_id": bug.get("client_id"),
            "metadata": bug.get("metadata", {}),
            "created_at": bug.get("created_at"),
        }

    def get_bug_status(self, report_id: str) -> dict | None:
        """Get just the status of a bug (for quick checks).

        Args:
            report_id: Bug report ID

        Returns:
            Status summary dict
        """
        bug = self.get_bug_report(report_id)
        if not bug:
            return None

        return {
            "report_id": bug["report_id"][:8],
            "title": bug["title"],
            "orty_status": bug["status"],
            "codey_status": bug["codey_status"],
            "codey_task_id": bug["codey_task_id"][:8] if bug["codey_task_id"] else None,
        }

    # === Action Tools ===

    def submit_task(
        self,
        task_type: str,
        title: str,
        description: str,
        workspace_ref: str,
        requirements: list[str] | None = None,
        acceptance_criteria: list[str] | None = None,
        forward_to_codey: bool = True,
    ) -> dict | None:
        """Submit a general task to Codey (feature, planning, refactoring, etc.).

        Args:
            task_type: Type of task (feature_request, planning_task, refactoring, etc.)
            title: Task title
            description: Full description
            workspace_ref: Target workspace (alfred, codey, orty, github:user/repo, etc.)
            requirements: List of requirements
            acceptance_criteria: Acceptance criteria
            forward_to_codey: Whether to forward to Codey automatically

        Returns:
            Created task info or None
        """
        logger.info(f"Submitting {task_type}: {title}")

        # For now, store as bug report with metadata (can be extended later)
        with self.bug_reports_repo.db.connect() as primary_client:
            row = primary_client.execute(
                "SELECT client_id FROM clients WHERE is_primary = 1 LIMIT 1"
            ).fetchone()
            client_id = row["client_id"] if row else "unknown"

        # Create as bug report with task type in metadata
        bug = self.bug_reports_repo.create_report(
            client_id=client_id,
            client="orty-chat",
            source=f"task-{task_type}",
            title=title,
            summary=description[:200],
            details=description,
            metadata={
                "task_type": task_type,
                "workspace_ref": workspace_ref,
                "requirements": requirements or [],
                "acceptance_criteria": acceptance_criteria or [],
            },
        )

        # Forward to Codey if requested
        if forward_to_codey and self.codey_processor:
            # Build Codey task payload for general tasks
            task_payload = {
                "task_type": task_type,
                "workspace_ref": workspace_ref,
                "requirements": requirements or [],
                "acceptance_criteria": acceptance_criteria or [],
            }

            codey_task = self.codey_processor.codey_client.create_task(
                task_type=task_type,
                source_product="orty",
                title=title,
                description=description,
                workspace_ref=workspace_ref,
                requested_by_client_id="orty_supervisor",
                task_payload=task_payload,
            )

            if codey_task.ok and codey_task.task:
                bug["codey_task_id"] = codey_task.task.get("task_id")
                bug["codey_status"] = codey_task.task.get("status")

        return bug

    def submit_bug_report(
        self,
        title: str,
        summary: str,
        details: str,
        client: str = "alfred-android",
        metadata: dict | None = None,
        forward_to_codey: bool = True,
    ) -> dict | None:
        """Submit a new bug report.

        Args:
            title: Bug title
            summary: Brief summary
            details: Full details
            client: Client identifier
            metadata: Additional metadata
            forward_to_codey: Whether to forward to Codey automatically

        Returns:
            Created bug report or None
        """
        logger.info(f"Submitting bug: {title}")

        # Get primary client ID for submission
        with self.bug_reports_repo.db.connect() as primary_client:
            row = primary_client.execute(
                "SELECT client_id FROM clients WHERE is_primary = 1 LIMIT 1"
            ).fetchone()
            client_id = row["client_id"] if row else "unknown"

        # Create bug report
        bug = self.bug_reports_repo.create_report(
            client_id=client_id,
            client=client,
            source="orty-chat",
            title=title,
            summary=summary,
            details=details,
            metadata=metadata or {},
        )

        # Forward to Codey if requested
        if forward_to_codey and self.codey_processor:
            codey_task = self.codey_processor.submit_to_codey(
                report_id=bug["report_id"],
                title=bug["title"],
                summary=bug["summary"],
                details=bug["details"],
                client_id=client_id,
                metadata=bug.get("metadata"),
            )
            if codey_task:
                bug["codey_task_id"] = codey_task.get("task_id")
                bug["codey_status"] = codey_task.get("status")

        return bug

    def forward_to_codey(self, report_id: str) -> dict | None:
        """Forward an existing bug to Codey.

        Args:
            report_id: Bug report ID

        Returns:
            Codey task info or None
        """
        if not self.codey_processor:
            logger.error("Codey processor not configured")
            return None

        bug = self.get_bug_report(report_id)
        if not bug:
            return None

        logger.info(f"Forwarding bug {report_id} to Codey")

        codey_task = self.codey_processor.submit_to_codey(
            report_id=bug["report_id"],
            title=bug["title"],
            summary=bug["summary"],
            details=bug["details"],
            client_id=bug["client_id"],
            metadata=bug.get("metadata"),
        )

        return codey_task

    def approve_codey_plan(self, report_id: str, approved_by: str = "orty_supervisor") -> dict | None:
        """Approve a Codey fix plan for a bug.

        Args:
            report_id: Bug report ID
            approved_by: Approver identifier

        Returns:
            Approval result or None
        """
        bug = self.get_bug_report(report_id)
        if not bug:
            return None

        if not bug.get("codey_task_id"):
            logger.error(f"Bug {report_id} has no Codey task")
            return None

        if not self.codey_processor:
            logger.error("Codey processor not configured")
            return None

        logger.info(f"Approving Codey plan for bug {report_id}")

        # Approve via Codey client
        approval_result = self.codey_processor.codey_client.approve_plan(
            bug["codey_task_id"],
            approved_by=approved_by,
        )

        return {
            "report_id": report_id,
            "codey_task_id": bug["codey_task_id"],
            "approved": approval_result.ok,
            "status": approval_result.task.get("status") if approval_result.task else None,
        }

    def reject_codey_plan(self, report_id: str, reason: str = "Plan rejected by Orty") -> dict | None:
        """Reject a Codey fix plan for a bug.

        Args:
            report_id: Bug report ID
            reason: Rejection reason

        Returns:
            Rejection result or None
        """
        bug = self.get_bug_report(report_id)
        if not bug:
            return None

        if not bug.get("codey_task_id"):
            return None

        if not self.codey_processor:
            return None

        logger.info(f"Rejecting Codey plan for bug {report_id}: {reason}")

        rejection_result = self.codey_processor.codey_client.reject_plan(
            bug["codey_task_id"],
            reason=reason,
        )

        return {
            "report_id": report_id,
            "codey_task_id": bug["codey_task_id"],
            "rejected": rejection_result.ok,
        }

    # === Analytics Tools ===

    def get_bug_stats(self) -> dict:
        """Get bug report statistics.

        Returns:
            Statistics summary
        """
        all_bugs = self.bug_reports_repo.list_reports(client_id=None, limit=1000)

        stats = {
            "total": len(all_bugs),
            "by_status": {},
            "by_codey_status": {},
            "by_client": {},
        }

        for bug in all_bugs:
            # Count by Orty status
            status = bug.get("status", "unknown")
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

            # Count by Codey status
            codey_status = bug.get("codey_status", "none")
            stats["by_codey_status"][codey_status] = stats["by_codey_status"].get(codey_status, 0) + 1

            # Count by client
            client = bug.get("client", "unknown")
            stats["by_client"][client] = stats["by_client"].get(client, 0) + 1

        return stats

    def search_bugs(self, query: str, limit: int = 20) -> list[dict]:
        """Search bugs by text query.

        Args:
            query: Search query (matches title, summary, details)
            limit: Maximum results

        Returns:
            Matching bug summaries
        """
        query_lower = query.lower()
        all_bugs = self.bug_reports_repo.list_reports(client_id=None, limit=200)

        matches = []
        for bug in all_bugs:
            # Search in title, summary, details
            text = f"{bug.get('title', '')} {bug.get('summary', '')} {bug.get('details', '')}".lower()
            if query_lower in text:
                matches.append({
                    "report_id": bug["report_id"][:8],
                    "title": bug["title"],
                    "status": bug.get("status"),
                    "codey_status": bug.get("codey_status"),
                    "relevance": "title" if query_lower in bug.get("title", "").lower() else "content",
                })

        # Sort by relevance (title matches first)
        matches.sort(key=lambda x: (x["relevance"] != "title", x["title"]))
        return matches[:limit]


# Convenience functions for direct use in conversation
_bug_tools: BugReportTools | None = None


def init_bug_tools(bug_reports_repo: BugReportsRepository, codey_processor: BugReportProcessor | None = None) -> BugReportTools:
    """Initialize global bug tools instance."""
    global _bug_tools
    _bug_tools = BugReportTools(bug_reports_repo, codey_processor)
    return _bug_tools


def get_bug_tools() -> BugReportTools | None:
    """Get global bug tools instance."""
    return _bug_tools
