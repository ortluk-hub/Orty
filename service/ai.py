from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
import base64
import inspect
from pathlib import Path
import re

import httpx

from service.config import settings

GenerateFn = Callable[[str, list[dict[str, str]]], Awaitable[str]]
ToolResult = str | Awaitable[str]
ToolFn = Callable[[str], ToolResult]


class AIService:
    def __init__(self):
        self.system_prompt = "You are Orty, a concise and intelligent on-device assistant."
        self._providers: dict[str, GenerateFn] = {
            "openai": self._generate_openai,
            "ollama": self._generate_ollama,
        }
        self._tools: dict[str, ToolFn] = {
            "echo": self._tool_echo,
            "utc_time": self._tool_utc_time,
            "fs_pwd": self._tool_fs_pwd,
            "fs_list": self._tool_fs_list,
            "fs_read": self._tool_fs_read,
            "gh_repo": self._tool_gh_repo,
            "gh_tree": self._tool_gh_tree,
            "gh_file": self._tool_gh_file,
        }

    def register_provider(self, name: str, generator: GenerateFn) -> None:
        self._providers[name.lower()] = generator

    def register_tool(self, name: str, tool: ToolFn) -> None:
        self._tools[name.lower()] = tool

    async def generate(self, message: str, history: list[dict[str, str]] | None = None) -> str:
        provider = settings.LLM_PROVIDER.lower()
        history = history or []

        tool_result = await self._maybe_execute_tool(message)
        if tool_result is not None:
            return tool_result

        generator = self._providers.get(provider)
        if generator is None:
            available = ", ".join(sorted(self._providers.keys()))
            return f"Unsupported LLM_PROVIDER '{provider}'. Available providers: {available}."

        return await generator(message, history)

    async def _generate_openai(self, message: str, history: list[dict[str, str]]) -> str:
        if not settings.OPENAI_API_KEY:
            return "OPENAI_API_KEY not configured."

        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": settings.OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                *history,
                {"role": "user", "content": message},
            ],
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
            )

        if response.status_code != 200:
            return f"OpenAI error: {response.text}"

        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def _generate_ollama(self, message: str, history: list[dict[str, str]]) -> str:
        payload = {
            "model": settings.OLLAMA_MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                *history,
                {"role": "user", "content": message},
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/chat",
                    json=payload,
                )
        except httpx.RequestError:
            return (
                "Ollama is not reachable. "
                f"Expected server at {settings.OLLAMA_BASE_URL}. "
                "Start Ollama locally or set LLM_PROVIDER=openai with OPENAI_API_KEY configured."
            )

        if response.status_code != 200:
            return f"Ollama error: {response.text}"

        data = response.json()
        return data["message"]["content"]

    async def _maybe_execute_tool(self, message: str) -> str | None:
        match = re.match(r"^\s*/tool\s+([a-zA-Z0-9_-]+)(?:\s+(.*))?$", message)
        if not match:
            return None

        tool_name = match.group(1).lower()
        tool_input = (match.group(2) or "").strip()

        tool = self._tools.get(tool_name)
        if tool is None:
            available = ", ".join(sorted(self._tools.keys()))
            return f"Tool '{tool_name}' is not available. Available tools: {available}."

        output = tool(tool_input)
        if inspect.isawaitable(output):
            return await output
        return output

    async def _tool_echo(self, tool_input: str) -> str:
        if not tool_input:
            return "(echo)"
        return tool_input

    async def _tool_utc_time(self, _: str) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    async def _tool_fs_pwd(self, _: str) -> str:
        return str(Path.cwd())

    async def _tool_fs_list(self, tool_input: str) -> str:
        target = Path(tool_input or ".")

        try:
            if not target.exists():
                return f"Path not found: {target}"
            if not target.is_dir():
                return f"Path is not a directory: {target}"

            items = [
                f"{entry.name}/" if entry.is_dir() else entry.name
                for entry in sorted(target.iterdir(), key=lambda entry: entry.name.lower())
            ]
        except OSError as exc:
            return f"Filesystem error: {exc}"

        if not items:
            return f"(empty directory) {target.resolve()}"
        return "\n".join(items)

    def _resolve_fs_read_target(self, raw_path: str) -> tuple[Path | None, str | None]:
        fs_read_root = Path(settings.FS_READ_ROOT).expanduser().resolve()

        expanded_input = Path(raw_path).expanduser()
        if expanded_input.is_absolute():
            candidate = expanded_input.resolve()
        else:
            candidate = (fs_read_root / expanded_input).resolve()

        try:
            candidate.relative_to(fs_read_root)
        except ValueError:
            return None, (
                f"Access denied: path must stay within FS_READ_ROOT ({fs_read_root})."
            )

        return candidate, None

    async def _tool_fs_read(self, tool_input: str) -> str:
        if not tool_input:
            return "Usage: /tool fs_read <path>"

        target, error = self._resolve_fs_read_target(tool_input)
        if error is not None or target is None:
            return error or "Access denied."

        try:
            if not target.exists():
                return f"Path not found: {target}"
            if target.is_dir():
                return f"Path is a directory: {target}"

            return target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return f"File is not UTF-8 text: {target}"
        except OSError as exc:
            return f"Filesystem error: {exc}"

    async def _github_get_json(self, endpoint: str) -> dict | list | None:
        url = f"https://api.github.com{endpoint}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "Orty-AIService",
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(url, headers=headers)
        except httpx.RequestError as exc:
            return {"error": f"GitHub request failed: {exc}"}

        if response.status_code != 200:
            return {"error": f"GitHub API error ({response.status_code}): {response.text}"}

        return response.json()

    async def _tool_gh_repo(self, tool_input: str) -> str:
        repo = tool_input.strip()
        if not repo or "/" not in repo:
            return "Usage: /tool gh_repo <owner/repo>"

        data = await self._github_get_json(f"/repos/{repo}")
        if isinstance(data, dict) and data.get("error"):
            return data["error"]
        if not isinstance(data, dict):
            return "Unexpected GitHub API response."

        return "\n".join(
            [
                f"name: {data.get('full_name', repo)}",
                f"description: {data.get('description') or '(none)'}",
                f"default_branch: {data.get('default_branch', '(unknown)')}",
                f"stars: {data.get('stargazers_count', 0)}",
                f"forks: {data.get('forks_count', 0)}",
                f"open_issues: {data.get('open_issues_count', 0)}",
                f"url: {data.get('html_url', f'https://github.com/{repo}')}",
            ]
        )

    async def _tool_gh_tree(self, tool_input: str) -> str:
        if not tool_input.strip():
            return "Usage: /tool gh_tree <owner/repo> [path]"

        parts = tool_input.split(maxsplit=1)
        repo = parts[0]
        subpath = parts[1].strip() if len(parts) > 1 else ""
        if "/" not in repo:
            return "Usage: /tool gh_tree <owner/repo> [path]"

        endpoint = f"/repos/{repo}/contents"
        if subpath:
            endpoint += f"/{subpath}"

        data = await self._github_get_json(endpoint)
        if isinstance(data, dict) and data.get("error"):
            return data["error"]
        if isinstance(data, dict):
            name = data.get("name", subpath or "/")
            kind = data.get("type", "file")
            return f"{name} ({kind})"
        if not isinstance(data, list):
            return "Unexpected GitHub API response."

        items = [f"{item.get('name', '?')}/" if item.get("type") == "dir" else item.get("name", "?") for item in data]
        return "\n".join(items) if items else "(empty)"

    async def _tool_gh_file(self, tool_input: str) -> str:
        parts = tool_input.split(maxsplit=2)
        if len(parts) < 2 or "/" not in parts[0]:
            return "Usage: /tool gh_file <owner/repo> <path> [ref]"

        repo = parts[0]
        file_path = parts[1]
        ref = parts[2].strip() if len(parts) == 3 else ""

        endpoint = f"/repos/{repo}/contents/{file_path}"
        if ref:
            endpoint = f"{endpoint}?ref={ref}"

        data = await self._github_get_json(endpoint)
        if isinstance(data, dict) and data.get("error"):
            return data["error"]
        if not isinstance(data, dict):
            return "Unexpected GitHub API response."
        if data.get("type") != "file":
            return f"Path is not a file: {file_path}"

        content = data.get("content", "")
        encoding = data.get("encoding", "")
        if encoding != "base64" or not content:
            return f"Unsupported GitHub content encoding: {encoding or '(none)'}"

        try:
            decoded = base64.b64decode(content, validate=False).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return "GitHub file is not valid UTF-8 text."

        return decoded
