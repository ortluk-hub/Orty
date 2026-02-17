from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
import re

import httpx

from service.config import settings

GenerateFn = Callable[[str, list[dict[str, str]]], Awaitable[str]]
ToolFn = Callable[[str], str]


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
        }

    def register_provider(self, name: str, generator: GenerateFn) -> None:
        self._providers[name.lower()] = generator

    def register_tool(self, name: str, tool: ToolFn) -> None:
        self._tools[name.lower()] = tool

    async def generate(self, message: str, history: list[dict[str, str]] | None = None) -> str:
        provider = settings.LLM_PROVIDER.lower()
        history = history or []

        tool_result = self._maybe_execute_tool(message)
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

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json=payload,
            )

        if response.status_code != 200:
            return f"Ollama error: {response.text}"

        data = response.json()
        return data["message"]["content"]

    def _maybe_execute_tool(self, message: str) -> str | None:
        match = re.match(r"^\s*/tool\s+([a-zA-Z0-9_-]+)(?:\s+(.*))?$", message)
        if not match:
            return None

        tool_name = match.group(1).lower()
        tool_input = (match.group(2) or "").strip()

        tool = self._tools.get(tool_name)
        if tool is None:
            available = ", ".join(sorted(self._tools.keys()))
            return f"Tool '{tool_name}' is not available. Available tools: {available}."

        return tool(tool_input)

    def _tool_echo(self, tool_input: str) -> str:
        if not tool_input:
            return "(echo)"
        return tool_input

    def _tool_utc_time(self, _: str) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _tool_fs_pwd(self, _: str) -> str:
        return str(Path.cwd())

    def _tool_fs_list(self, tool_input: str) -> str:
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

    def _tool_fs_read(self, tool_input: str) -> str:
        if not tool_input:
            return "Usage: /tool fs_read <path>"

        target = Path(tool_input)
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
