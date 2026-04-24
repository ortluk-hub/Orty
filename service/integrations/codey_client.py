"""Codey client for Orty integration.

This module provides HTTP client for Orty to submit bug reports to Codey's task API.
"""

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, request


@dataclass(frozen=True)
class CodeyTaskResponse:
    """Response from Codey task operations."""

    ok: bool
    task: dict | None = None
    events: list[dict] | None = None
    artifact: dict | None = None
    result: dict | None = None
    error: str | None = None
    detail: str | None = None


class CodeyClient:
    """HTTP client for Orty to interact with Codey task API.

    Submits bug reports from Orty to Codey as tasks for automated processing.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
    ):
        """Initialize Codey client.

        Args:
            base_url: Codey API base URL (e.g., "http://localhost:8000")
            api_key: Optional API key for authentication
            timeout_seconds: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def submit_bug_report(
        self,
        title: str,
        description: str,
        source_product: str = "alfred",
        workspace_ref: str = "",
        conversation_id: str = "",
        task_payload: dict | None = None,
        priority: str = "normal",
    ) -> CodeyTaskResponse:
        """Submit a bug report to Codey as a task.

        Args:
            title: Bug report title
            description: Bug description
            source_product: Product name (e.g., "alfred", "orty")
            workspace_ref: Workspace path for code fixes
            conversation_id: Original conversation ID from Alfred
            task_payload: Additional bug-specific payload
            priority: Task priority ("low", "normal", "high")

        Returns:
            CodeyTaskResponse with task details or error
        """
        payload = {
            "task_type": "bug_report",
            "source_product": source_product,
            "title": title,
            "description": description,
            "conversation_id": conversation_id,
            "workspace_ref": workspace_ref,
            "task_payload": task_payload or {},
            "priority": priority,
            "approval_mode": "auto",
            "requested_by_client_id": "orty-supervisor",
        }

        return self._post("/tasks", payload)

    def get_task(self, task_id: str) -> CodeyTaskResponse:
        """Get task details by ID.

        Reads directly from Codey's task storage for efficiency.

        Args:
            task_id: Task identifier

        Returns:
            CodeyTaskResponse with task details or error
        """
        import json
        from pathlib import Path

        # Read task directly from Codey's storage
        task_file = Path(f"/home/ortluk/ortluk-hub/Codey/data/tasks/{task_id}/task.json")

        if not task_file.exists():
            return CodeyTaskResponse(ok=False, error="Task not found")

        try:
            with open(task_file) as f:
                task_data = json.load(f)
            return CodeyTaskResponse(ok=True, task=task_data)
        except Exception as e:
            return CodeyTaskResponse(ok=False, error=str(e))

    def get_artifact(self, task_id: str, artifact_type: str) -> CodeyTaskResponse:
        """Get task artifact by type.

        Reads directly from Codey's artifact storage.

        Args:
            task_id: Task identifier
            artifact_type: Artifact type (e.g., "bug_triage", "fix_plan")

        Returns:
            CodeyTaskResponse with artifact or error
        """
        import json
        from pathlib import Path

        # Read artifact directly from Codey's storage
        artifact_file = Path(f"/home/ortluk/ortluk-hub/Codey/data/tasks/{task_id}/artifacts/{artifact_type}.json")

        if not artifact_file.exists():
            return CodeyTaskResponse(ok=False, error="Artifact not found")

        try:
            with open(artifact_file) as f:
                artifact_data = json.load(f)
            return CodeyTaskResponse(ok=True, artifact=artifact_data)
        except Exception as e:
            return CodeyTaskResponse(ok=False, error=str(e))

    def list_events(self, task_id: str, limit: int = 100) -> CodeyTaskResponse:
        """List task events."""
        return self._get(f"/tasks/{task_id}/events?limit={limit}")

    def approve_plan(
        self,
        task_id: str,
        approved_by: str = "orty_supervisor",
    ) -> CodeyTaskResponse:
        """Approve a fix plan.

        Args:
            task_id: Task identifier
            approved_by: Approver identifier

        Returns:
            CodeyTaskResponse or error
        """
        return self._post(f"/tasks/{task_id}/approve", {"approved_by": approved_by})

    def plan_task(self, task_id: str, timeout_seconds: float = 600.0) -> CodeyTaskResponse:
        """Request fix plan generation.

        Args:
            task_id: Task identifier
            timeout_seconds: Timeout for plan generation (default 600s for LLM)

        Returns:
            CodeyTaskResponse or error
        """
        return self._post(f"/tasks/{task_id}/plan", {}, timeout_seconds=timeout_seconds)

    def execute_tracing(
        self,
        task_id: str,
        tracing_plan: dict,
    ) -> CodeyTaskResponse:
        """Execute tracing plan for low-confidence bugs.

        Note: This calls the triage endpoint which handles tracing.

        Args:
            task_id: Task identifier
            tracing_plan: Tracing plan from triage

        Returns:
            CodeyTaskResponse with tracing results or error
        """
        # For now, use triage endpoint - tracing is part of triage
        return self._post(f"/tasks/{task_id}/triage", {})

    def execute_task(
        self,
        task_id: str,
        patches: list[dict],
    ) -> CodeyTaskResponse:
        """Execute implementation patches.

        Args:
            task_id: Task identifier
            patches: List of patch operations

        Returns:
            CodeyTaskResponse or error
        """
        return self._post(f"/tasks/{task_id}/execute", {"patches": patches})

    def verify_task(self, task_id: str) -> CodeyTaskResponse:
        """Run verification tests.

        Args:
            task_id: Task identifier

        Returns:
            CodeyTaskResponse with verification results or error
        """
        return self._post(f"/tasks/{task_id}/verify", {"command_type": "test", "command": "pytest -q"})

    def approve_plan(self, task_id: str, approved_by: str = "orty_supervisor") -> CodeyTaskResponse:
        """Approve a fix plan for a task.

        Args:
            task_id: Task identifier
            approved_by: Approver identifier (e.g., "orty_supervisor", user ID)

        Returns:
            CodeyTaskResponse with updated task or error
        """
        return self._post(f"/tasks/{task_id}/approve", {"approved_by": approved_by})

    def reset_task(self, task_id: str) -> CodeyTaskResponse:
        """Reset a task status to allow retry after execution failure.

        Args:
            task_id: Task identifier

        Returns:
            CodeyTaskResponse or error
        """
        return self._post(f"/tasks/{task_id}/reset", {})

    def poll_task(
        self,
        task_id: str,
        interval_seconds: float = 1.0,
        timeout_seconds: float = 300.0,
    ) -> CodeyTaskResponse:
        """Poll task until completion or timeout.

        Args:
            task_id: Task identifier
            interval_seconds: Polling interval
            timeout_seconds: Maximum wait time

        Returns:
            CodeyTaskResponse with final task state or timeout error
        """
        import time
        start_time = time.time()
        terminal_statuses = {"completed", "failed", "cancelled"}

        while time.time() - start_time < timeout_seconds:
            response = self.get_task(task_id)
            if not response.ok:
                return response

            task = response.task
            if task and task.get("status") in terminal_statuses:
                return response

            time.sleep(interval_seconds)

        return CodeyTaskResponse(
            ok=False,
            error="timeout",
            detail=f"Task {task_id} did not complete within {timeout_seconds} seconds",
        )

    def _get(self, path: str) -> CodeyTaskResponse:
        """Make GET request to Codey API."""
        url = f"{self.base_url}{path}"
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = request.Request(url, headers=headers, method="GET")
        return self._request(req)

    def _post(self, path: str, data: dict, timeout_seconds: float | None = None) -> CodeyTaskResponse:
        """Make POST request to Codey API.

        Args:
            path: API path
            data: Request body
            timeout_seconds: Optional timeout override
        """
        url = f"{self.base_url}{path}"
        body = json.dumps(data).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = request.Request(url, data=body, headers=headers, method="POST")
        return self._request(req, timeout_seconds=timeout_seconds)

    def _request(self, req: request.Request, timeout_seconds: float | None = None) -> CodeyTaskResponse:
        """Execute HTTP request and parse response.

        Args:
            req: Request object
            timeout_seconds: Optional timeout override
        """
        timeout = timeout_seconds if timeout_seconds is not None else self.timeout_seconds
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)
                # Check if response is an artifact (has artifact_id) or a task (has task_id)
                is_artifact = isinstance(data, dict) and "artifact_id" in data
                is_task = isinstance(data, dict) and "task_id" in data
                return CodeyTaskResponse(
                    ok=True,
                    task=data if is_task else None,
                    events=data.get("events") if isinstance(data, dict) else None,
                    artifact=data if is_artifact else None,
                    result=data if isinstance(data, dict) else None,  # Include full response in result
                )
        except error.HTTPError as exc:
            try:
                error_body = exc.read().decode("utf-8")
                error_data = json.loads(error_body)
                detail = error_data.get("detail", str(exc))
            except Exception:
                detail = str(exc)
            return CodeyTaskResponse(
                ok=False,
                error="http_error",
                detail=f"HTTP {exc.code}: {detail}",
            )
        except TimeoutError:
            return CodeyTaskResponse(
                ok=False,
                error="timeout",
                detail="Request timed out",
            )
        except error.URLError as exc:
            return CodeyTaskResponse(
                ok=False,
                error="connection_error",
                detail=f"Connection failed: {exc.reason}",
            )
        except json.JSONDecodeError as exc:
            return CodeyTaskResponse(
                ok=False,
                error="invalid_response",
                detail=f"Invalid JSON response: {exc}",
            )
