"""Bug report processor for Orty-Codey integration.

Orty manages the COMPLETE task lifecycle with ITERATIVE fix attempts:
1. Receive bug report
2. Submit to Codey for TRIAGE
3. Review triage results (confidence, subsystems)
4. ITERATIVE FIX ATTEMPTS (up to max_attempts):
   - Generate patch attempt (even low confidence - safe in clone)
   - Apply to cloned workspace
   - Run verification tests
   - If GREEN (tests pass) → complete and ready for merge
   - If RED (tests fail) → try different approach
5. Only mark COMPLETE when tests pass (GREEN)
6. Mark FAILED if all attempts fail

Orty is the supervisor - Codey is the worker.
Safety: All fixes in cloned workspace, original never at risk.
"""

import logging
from typing import Any
from enum import Enum

from service.integrations.codey_client import CodeyClient
from service.storage.bug_reports_repo import BugReportsRepository


logger = logging.getLogger(__name__)


class TaskPhase(Enum):
    """Task lifecycle phases managed by Orty."""
    TRIAGE = "triage"
    ITERATING = "iterating"  # Multiple fix attempts
    APPROVED = "approved"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    COMPLETE = "complete"  # GREEN - tests passed
    FAILED = "failed"  # All attempts failed


class BugReportProcessor:
    """Process bug reports with iterative fix attempts.

    Orty supervises each phase:
    - Triage: Codey analyzes bug
    - Iteration: Codey tries fixes in cloned workspace (safe)
    - Approval: Auto-approve for iteration
    - Execution: Codey applies patches to clone
    - Verification: Codey runs tests
    - Complete: Only if tests GREEN
    """

    def __init__(
        self,
        codey_client: CodeyClient,
        workspace_ref: str = "",
        bug_reports_repo: BugReportsRepository | None = None,
        auto_approve_low_risk: bool = True,
        notify_user_on_plan: bool = True,
        require_approval_for_high_risk: bool = True,
    ):
        """Initialize bug report processor.

        Args:
            codey_client: Codey HTTP client
            workspace_ref: Default workspace path for bug fixes
            bug_reports_repo: Repository for updating bug status
            auto_approve_low_risk: Auto-approve for iteration
            notify_user_on_plan: Notify user when plan is ready
            require_approval_for_high_risk: Require user approval for merge
        """
        self.codey_client = codey_client
        self.workspace_ref = workspace_ref
        self.bug_reports_repo = bug_reports_repo
        self.auto_approve_low_risk = auto_approve_low_risk
        self.notify_user_on_plan = notify_user_on_plan
        self.require_approval_for_high_risk = require_approval_for_high_risk

    def process_bug_lifecycle(
        self,
        report_id: str,
        title: str,
        summary: str,
        details: str,
        client_id: str,
        metadata: dict | None = None,
        max_attempts: int = 3,
    ) -> dict | None:
        """Process a bug through the COMPLETE Orty-supervised lifecycle.

        Lifecycle with ITERATION:
        1. Submit for TRIAGE
        2. Review triage (confidence, subsystems)
        3. ITERATIVE FIX ATTEMPTS (up to max_attempts):
           - Generate patch attempt (low confidence OK - safe in clone)
           - Apply to cloned workspace
           - Run verification tests
           - If GREEN → complete
           - If RED → try different approach
        4. Only mark COMPLETE when tests pass (GREEN)
        5. Mark FAILED if all attempts fail

        Args:
            report_id: Orty bug report ID
            title: Bug title
            summary: Bug summary
            details: Bug details
            client_id: Client ID
            metadata: Additional metadata
            max_attempts: Maximum fix attempts before giving up

        Returns:
            Final task status or None if failed
        """
        logger.info(f"Starting bug lifecycle for {report_id}: {title}")

        # Phase 1: Submit for TRIAGE
        logger.info(f"Phase 1: TRIAGE - Submitting {report_id} to Codey")
        task = self._submit_for_triage(report_id, title, summary, details, client_id, metadata)

        if not task:
            logger.error(f"Failed to submit {report_id} for triage")
            return None

        task_id = task.get("task_id")
        self._update_bug_status(report_id, "in_triage", task_id)

        # Phase 2: Wait for and review triage results
        logger.info(f"Phase 2: Reviewing triage for {report_id}")
        triage_result = self._poll_for_triage(task_id)

        if not triage_result:
            logger.error(f"Failed to get triage result for {report_id}")
            return None

        confidence = triage_result.get("confidence", 0)
        logger.info(f"Triage complete: confidence={confidence:.0%}")

        # NOTE: We proceed EVEN with low confidence
        # Low confidence = more attempts, not blocked
        # Codey can try fixes in cloned workspace safely

        # Phase 3-5: ITERATIVE FIX ATTEMPTS
        logger.info(f"Phase 3-5: ITERATIVE FIX - Up to {max_attempts} attempts for {report_id}")

        for attempt in range(1, max_attempts + 1):
            logger.info(f"=== Fix Attempt {attempt}/{max_attempts} for {report_id} ===")

            # Request fix plan with patch generation
            logger.info(f"Requesting fix plan (attempt {attempt})")
            plan_result = self._request_fix_plan(task_id, attempt=attempt, triage=triage_result)

            if not plan_result:
                logger.warning(f"Failed to get fix plan for attempt {attempt}")
                continue

            # Check if plan has patches
            patches = plan_result.get("patches", [])
            if not patches:
                logger.warning(f"No patches in plan for attempt {attempt}, trying different approach")
                continue

            # Review and approve plan (auto-approve for iteration)
            logger.info(f"Approving plan for attempt {attempt}")
            self._approve_plan_auto(task_id)
            self._update_bug_status(report_id, "plan_approved", task_id)

            # Execute implementation
            logger.info(f"Executing fix (attempt {attempt})")
            execution_result = self._execute_implementation(task_id, plan_result)

            if not execution_result:
                logger.warning(f"Execution failed for attempt {attempt}")
                # Reset task status in Codey to allow re-planning
                self.codey_client.reset_task(task_id)
                self._update_bug_status(report_id, "triaged", task_id)
                continue

            # Check if execution was successful
            result_ok = execution_result.get("result", {}).get("ok", False)
            if not result_ok:
                logger.warning(f"Patch application failed for attempt {attempt}")
                # Reset task status in Codey to allow re-planning
                self.codey_client.reset_task(task_id)
                self._update_bug_status(report_id, "triaged", task_id)
                continue

            self._update_bug_status(report_id, "executing", task_id)

            # Run verification
            logger.info(f"Running verification (attempt {attempt})")
            verification_result = self._run_verification(task_id, execution_result)

            if verification_result and verification_result.get("passed"):
                # SUCCESS! Tests passed (GREEN)
                logger.info(f"✓ Attempt {attempt} PASSED verification (GREEN)!")
                self._update_bug_status(report_id, "fixed_verified", task_id)
                return {
                    "report_id": report_id,
                    "task_id": task_id,
                    "final_phase": TaskPhase.COMPLETE.value,
                    "success": True,
                    "attempts": attempt,
                }
            else:
                # FAILED (RED) - try different approach
                logger.warning(f"✗ Attempt {attempt} FAILED verification (RED), trying different approach")
                self._update_bug_status(report_id, "verification_failed_retry", task_id)

        # All attempts failed
        logger.error(f"✗ All {max_attempts} attempts failed for {report_id}")
        self._update_bug_status(report_id, "fix_verification_failed", task_id)
        return {
            "report_id": report_id,
            "task_id": task_id,
            "final_phase": TaskPhase.FAILED.value,
            "success": False,
            "attempts": max_attempts,
        }

    def submit_to_codey(
        self,
        report_id: str,
        title: str,
        summary: str,
        details: str,
        client_id: str,
        metadata: dict | None = None,
        source_created_at: int | None = None,
    ) -> dict | None:
        """Submit a bug to Codey for the initial triage task.

        API routes and conversational flows use this lightweight handoff path.
        The full iterative lifecycle remains available through
        ``process_bug_lifecycle()``.
        """
        del source_created_at
        return self._submit_for_triage(
            report_id=report_id,
            title=title,
            summary=summary,
            details=details,
            client_id=client_id,
            metadata=metadata,
        )

    def _submit_for_triage(
        self,
        report_id: str,
        title: str,
        summary: str,
        details: str,
        client_id: str,
        metadata: dict | None = None,
    ) -> dict | None:
        """Submit bug for triage only (not full fix)."""
        description = f"{summary}\n\n{details}"
        workspace_ref = self.workspace_ref

        task_payload = {
            "orty_report_id": report_id,
            "orty_client_id": client_id,
            "metadata": metadata or {},
            "approval_mode": "orty_supervised",
            "lifecycle_phase": "triage",  # Only triage for now
        }

        response = self.codey_client.submit_bug_report(
            title=title,
            description=description,
            source_product="alfred",
            workspace_ref=workspace_ref,
            conversation_id=f"orty-bug-{report_id}",
            task_payload=task_payload,
            priority=self._infer_priority(summary, details),
        )

        if response.ok and response.task:
            task_id = response.task.get("task_id")
            logger.info(f"Bug {report_id} submitted for triage as task {task_id}")
            return response.task

        logger.error(f"Failed to submit {report_id} for triage: {response.error}")
        return None

    def _poll_for_triage(self, task_id: str, max_polls: int = 30, poll_interval: int = 4) -> dict | None:
        """Poll Codey for triage completion."""
        import time

        # First, trigger triage
        logger.info(f"Triggering triage for {task_id}")
        triage_response = self.codey_client._post(f"/tasks/{task_id}/triage", {})

        if not triage_response.ok:
            logger.warning(f"Failed to trigger triage: {triage_response.error}")

        for i in range(max_polls):
            task_response = self.codey_client.get_task(task_id)

            if not task_response.ok:
                logger.warning(f"Failed to get task {task_id} status")
                time.sleep(poll_interval)
                continue

            task = task_response.task
            status = task.get("status", "")

            if status == "triaged":
                logger.info(f"Triage complete for {task_id}")
                # Get triage artifact
                artifact_response = self.codey_client.get_artifact(task_id, "bug_triage")
                if artifact_response.ok and artifact_response.artifact:
                    return artifact_response.artifact.get("payload", {})

            time.sleep(poll_interval)

        # If we get here, check one more time - triage might have completed
        logger.info(f"Final check for {task_id}")
        task_response = self.codey_client.get_task(task_id)
        if task_response.ok and task_response.task.get("status") == "triaged":
            artifact_response = self.codey_client.get_artifact(task_id, "bug_triage")
            if artifact_response.ok and artifact_response.artifact:
                logger.info(f"Triage completed (late) for {task_id}")
                return artifact_response.artifact.get("payload", {})

        logger.error(f"Triage timeout for {task_id} after {max_polls * poll_interval}s")
        return None

    def _request_fix_plan(
        self,
        task_id: str,
        attempt: int = 1,
        triage: dict | None = None,
    ) -> dict | None:
        """Request fix plan from Codey with attempt number for iteration."""
        logger.info(f"Requesting fix plan for {task_id} (attempt {attempt})")

        # Call Codey's plan endpoint
        response = self.codey_client.plan_task(task_id)

        if response.ok and response.task:
            # Get plan artifact
            artifact_response = self.codey_client.get_artifact(task_id, "fix_plan")
            if artifact_response.ok and artifact_response.artifact:
                return artifact_response.artifact.get("payload", {})

        logger.error(f"Failed to get fix plan for {task_id}: {response.error if response else 'No response'}")
        return None

    def _approve_plan_auto(self, task_id: str) -> bool:
        """Auto-approve plan for iteration."""
        response = self.codey_client.approve_plan(task_id, approved_by="orty_supervisor")
        return response.ok

    def _execute_implementation(self, task_id: str, plan_result: dict) -> dict | None:
        """Execute the approved fix plan."""
        logger.info(f"Executing implementation for {task_id}")

        # Get patches from plan
        patches = plan_result.get("patches", [])

        if not patches:
            logger.warning(f"No patches in plan for {task_id}, cannot execute")
            return None

        response = self.codey_client.execute_task(task_id, patches=patches)

        if response.ok:
            return response.result

        logger.error(f"Execution failed for {task_id}: {response.error}")
        return None

    def _run_verification(self, task_id: str, execution_result: dict) -> dict | None:
        """Run verification tests."""
        logger.info(f"Running verification for {task_id}")

        response = self.codey_client.verify_task(task_id)

        if response.ok:
            # Check task status from response
            if response.task:
                status = response.task.get("status", "")
                if status == "completed":
                    return {"passed": True}
                elif status == "failed":
                    return {"passed": False, "reason": "tests_failed"}
            # Check result from response (artifact response)
            if response.result:
                result = response.result.get("result", {})
                if result.get("passed"):
                    return {"passed": True}
                elif result.get("failed"):
                    return {"passed": False, "reason": result.get("summary", "unknown")}

        logger.warning(f"Verification failed for {task_id}: {response.error or response.detail}")
        return {"passed": False, "reason": response.error or response.detail or "unknown"}

    def _update_bug_status(self, report_id: str, status: str, codey_task_id: str | None) -> None:
        """Update bug report status in database."""
        if self.bug_reports_repo:
            self.bug_reports_repo.update_bug_status(report_id, status, codey_task_id)
            logger.debug(f"Bug {report_id} status updated to {status}")

    def _infer_priority(self, summary: str, details: str) -> str:
        """Infer bug priority from content."""
        text = (summary + " " + details).lower()

        critical_keywords = ["crash", "data loss", "security", "broken", "fails"]
        if any(kw in text for kw in critical_keywords):
            return "high"

        low_keywords = ["cosmetic", "typo", "minor", "suggestion"]
        if any(kw in text for kw in low_keywords):
            return "low"

        return "normal"
