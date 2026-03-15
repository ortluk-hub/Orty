from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
import base64
from dataclasses import dataclass
from html import unescape
import inspect
import json
from pathlib import Path
import re
from typing import TypedDict

import httpx

from service.config import settings

GenerateFn = Callable[[str, list[dict[str, str]]], Awaitable[str]]
ToolResult = str | Awaitable[str]
ToolFn = Callable[[str], ToolResult]
TOOL_INPUT_MAX_LENGTH = 2000
REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
RESULT_BLOCK_SPLIT_PATTERN = re.compile(r'(?=<div class="result results_links)')
RESULT_LINK_PATTERN = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.S,
)
RESULT_SNIPPET_PATTERN = re.compile(
    r'<(?:a|div)[^>]*class="result__snippet"[^>]*>(?P<snippet>.*?)</(?:a|div)>',
    re.S,
)
TAG_PATTERN = re.compile(r"<[^>]+>")
TIME_LIKE_PATTERN = re.compile(r"\b\d{1,2}(?::\d{2})?\s?(?:a\.?m\.?|p\.?m\.?)\b", re.I)
HOURS_HINT_PATTERN = re.compile(r"\b(open|close|closing|hour|hours)\b", re.I)
SEARCH_RESULT_LIMIT = 3
SMART_HOME_POLITE_PREFIX = re.compile(r"^\s*(?:please\s+)+", re.I)


@dataclass
class WebSearchResult:
    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class SmartHomeDevice:
    name: str
    device_id: str
    kind: str
    component: str = "main"
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class SmartHomeRequest:
    action: str
    target: str
    value: int | None = None


class GenerationResult(TypedDict):
    reply: str
    provider: str
    handled_by: str
    fallback_used: bool
    fallback_provider: str | None


class AIService:
    def __init__(self):
        self.system_prompt = "You are Orty, a concise and intelligent on-device assistant."
        self._providers: dict[str, GenerateFn] = {
            "openai": self._generate_openai,
            "ollama": self._generate_ollama,
            "ollama_cloud": self._generate_ollama_cloud,
        }
        self._tools: dict[str, ToolFn] = {
            "echo": self._tool_echo,
            "utc_time": self._tool_utc_time,
            "web_search": self._tool_web_search,
            "smart_home": self._tool_smart_home,
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
        result = await self.generate_with_meta(message, history=history)
        return result["reply"]

    async def generate_with_meta(self, message: str, history: list[dict[str, str]] | None = None) -> GenerationResult:
        provider = settings.LLM_PROVIDER.lower()
        history = history or []

        tool_result = await self._maybe_execute_tool(message)
        if tool_result is not None:
            return {
                "reply": tool_result,
                "provider": "tool",
                "handled_by": "tool",
                "fallback_used": False,
                "fallback_provider": None,
            }

        generator = self._providers.get(provider)
        if generator is None:
            available = ", ".join(sorted(self._providers.keys()))
            return {
                "reply": f"Unsupported LLM_PROVIDER '{provider}'. Available providers: {available}.",
                "provider": provider,
                "handled_by": "unsupported-provider",
                "fallback_used": False,
                "fallback_provider": None,
            }

        primary_reply = await generator(message, history)
        if not self._should_attempt_cloud_fallback(provider, primary_reply):
            return {
                "reply": primary_reply,
                "provider": provider,
                "handled_by": self._handled_by_for_provider(provider, fallback_used=False),
                "fallback_used": False,
                "fallback_provider": None,
            }

        fallback_provider = settings.CLOUD_FALLBACK_PROVIDER.lower()
        fallback_generator = self._providers.get(fallback_provider)
        if fallback_generator is None:
            return {
                "reply": primary_reply,
                "provider": provider,
                "handled_by": self._handled_by_for_provider(provider, fallback_used=False),
                "fallback_used": False,
                "fallback_provider": None,
            }

        fallback_reply = await fallback_generator(message, history)
        if self._is_provider_error(fallback_provider, fallback_reply):
            return {
                "reply": (
                    f"{primary_reply}\n\n"
                    f"Cloud fallback ({fallback_provider}) also failed: {fallback_reply}"
                ),
                "provider": provider,
                "handled_by": self._handled_by_for_provider(provider, fallback_used=False),
                "fallback_used": False,
                "fallback_provider": fallback_provider,
            }
        return {
            "reply": fallback_reply,
            "provider": fallback_provider,
            "handled_by": self._handled_by_for_provider(fallback_provider, fallback_used=True),
            "fallback_used": True,
            "fallback_provider": fallback_provider,
        }

    def _is_provider_error(self, provider: str, reply: str) -> bool:
        normalized = provider.lower()
        if normalized in {"ollama", "ollama_cloud"}:
            return reply.startswith("Ollama is not reachable.") or reply.startswith("Ollama error:")
        if normalized == "openai":
            return reply == "OPENAI_API_KEY not configured." or reply.startswith("OpenAI error:")
        return False

    def _should_attempt_cloud_fallback(self, provider: str, primary_reply: str) -> bool:
        if not settings.ENABLE_CLOUD_FALLBACK:
            return False
        fallback_provider = settings.CLOUD_FALLBACK_PROVIDER.lower()
        if not fallback_provider or fallback_provider == provider.lower():
            return False
        return self._is_provider_error(provider, primary_reply)

    def _handled_by_for_provider(self, provider: str, *, fallback_used: bool) -> str:
        normalized = provider.lower()
        if fallback_used:
            return "cloud-fallback"
        if normalized == "ollama":
            return "orty-local"
        if normalized in {"openai", "ollama_cloud"}:
            return "cloud-primary"
        return normalized

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
        return await self._generate_ollama_with_model(settings.OLLAMA_MODEL, message, history)

    async def _generate_ollama_cloud(self, message: str, history: list[dict[str, str]]) -> str:
        model = settings.OLLAMA_CLOUD_FALLBACK_MODEL.strip()
        if not model:
            return "Ollama error: cloud fallback model not configured."
        return await self._generate_ollama_with_model(model, message, history)

    async def _generate_ollama_with_model(self, model: str, message: str, history: list[dict[str, str]]) -> str:
        payload = {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                *history,
                {"role": "user", "content": message},
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=180) as client:
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
        if len(tool_input) > TOOL_INPUT_MAX_LENGTH:
            return (
                f"Tool input exceeds {TOOL_INPUT_MAX_LENGTH} characters. "
                "Please provide a shorter input."
            )

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

    async def _tool_web_search(self, tool_input: str) -> str:
        query = tool_input.strip()
        if not query:
            return "Usage: /tool web_search <question>"

        try:
            results = await self._search_web(query)
        except httpx.RequestError as exc:
            return f"Web search failed: {exc}"
        except ValueError as exc:
            return str(exc)

        if not results:
            return f"No web search results found for '{query}'."

        best = self._select_best_web_result(query, results)
        summary = self._truncate_text(best.snippet or best.title, 260)
        reply_lines = [f"I found this on the web: {best.title}."]
        if summary and summary != best.title:
            reply_lines.append(summary)
        reply_lines.append(f"Source: {best.url}")
        return "\n".join(reply_lines)

    async def _tool_smart_home(self, tool_input: str) -> str:
        command_text = tool_input.strip()
        if not command_text:
            return "Usage: /tool smart_home <command>"

        if settings.SMART_HOME_PROVIDER != "smartthings":
            return (
                "Smart-home control unavailable: configure SMART_HOME_PROVIDER=smartthings, "
                "SMARTTHINGS_PAT, and SMARTTHINGS_DEVICE_MAP on Orty."
            )

        if not settings.SMARTTHINGS_PAT:
            return "Smart-home control unavailable: SMARTTHINGS_PAT is not configured."

        devices = self._load_smartthings_devices()
        if not devices:
            return (
                "Smart-home control unavailable: SMARTTHINGS_DEVICE_MAP is empty or invalid."
            )

        parsed = self._parse_smart_home_request(command_text)
        if parsed is None:
            return (
                "I couldn't parse that smart-home command. "
                "Try phrases like 'turn off the living room lights' or "
                "'set the thermostat to 68'."
            )

        device = self._match_smart_home_device(parsed.target, devices)
        if device is None:
            return (
                f"I couldn't find a configured smart-home device matching '{parsed.target}'."
            )

        command_body, success_reply = self._build_smartthings_command(device, parsed)
        if command_body is None or success_reply is None:
            return (
                f"I couldn't map '{command_text}' to a supported command for {device.name}. "
                "Check the device kind in SMARTTHINGS_DEVICE_MAP."
            )

        try:
            await self._smartthings_send_command(device.device_id, command_body)
        except httpx.RequestError as exc:
            return f"Smart-home request failed: {exc}"
        except ValueError as exc:
            return str(exc)

        return success_reply

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
        if not REPO_PATTERN.fullmatch(repo):
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
        if not REPO_PATTERN.fullmatch(repo):
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
        if len(parts) < 2 or not REPO_PATTERN.fullmatch(parts[0]):
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

    def _load_smartthings_devices(self) -> list[SmartHomeDevice]:
        raw = settings.SMARTTHINGS_DEVICE_MAP.strip()
        if not raw:
            return []

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []

        entries: list[dict] = []
        if isinstance(payload, dict):
            for alias, config in payload.items():
                if isinstance(config, str):
                    entries.append(
                        {
                            "name": alias,
                            "device_id": config,
                            "kind": "switch",
                            "aliases": [alias],
                        }
                    )
                elif isinstance(config, dict):
                    merged = dict(config)
                    merged.setdefault("name", alias)
                    aliases = list(merged.get("aliases") or [])
                    aliases.append(alias)
                    merged["aliases"] = aliases
                    entries.append(merged)
        elif isinstance(payload, list):
            entries = [item for item in payload if isinstance(item, dict)]

        devices: list[SmartHomeDevice] = []
        for entry in entries:
            device_id = str(entry.get("device_id") or entry.get("id") or "").strip()
            name = str(entry.get("name") or "").strip()
            kind = str(entry.get("kind") or "switch").strip().lower()
            component = str(entry.get("component") or "main").strip() or "main"
            aliases = tuple(
                {
                    self._normalize_smart_home_alias(alias)
                    for alias in [name, *(entry.get("aliases") or [])]
                    if str(alias).strip()
                }
            )
            if not device_id or not name or not aliases:
                continue
            devices.append(
                SmartHomeDevice(
                    name=name,
                    device_id=device_id,
                    kind=kind,
                    component=component,
                    aliases=aliases,
                )
            )

        return devices

    def _parse_smart_home_request(self, command_text: str) -> SmartHomeRequest | None:
        normalized = self._normalize_smart_home_alias(command_text)
        normalized = SMART_HOME_POLITE_PREFIX.sub("", normalized).strip()
        normalized = re.sub(r"\s+", " ", normalized)
        if not normalized:
            return None

        for prefix, action in (
            ("turn on ", "on"),
            ("switch on ", "on"),
            ("turn off ", "off"),
            ("switch off ", "off"),
            ("lock ", "lock"),
            ("unlock ", "unlock"),
            ("open ", "open"),
            ("close ", "close"),
            ("start ", "on"),
            ("stop ", "off"),
        ):
            if normalized.startswith(prefix):
                target = self._normalize_smart_home_target(normalized[len(prefix):])
                return SmartHomeRequest(action=action, target=target) if target else None

        value_match = re.match(
            r"^(set|dim|brighten|raise|lower)\s+(.+?)\s+to\s+(\d{1,3})(?:\s*(?:degrees?|percent))?\s*$",
            normalized,
        )
        if value_match:
            action_word = value_match.group(1)
            target = self._normalize_smart_home_target(value_match.group(2))
            value = int(value_match.group(3))
            if not target:
                return None
            if action_word in {"dim", "brighten"}:
                return SmartHomeRequest(action="set_level", target=target, value=value)
            return SmartHomeRequest(action="set_value", target=target, value=value)

        return None

    def _match_smart_home_device(
        self,
        target: str,
        devices: list[SmartHomeDevice]
    ) -> SmartHomeDevice | None:
        normalized_target = self._normalize_smart_home_target(target)
        if not normalized_target:
            return None

        candidates = sorted(
            (
                device
                for device in devices
                if any(
                    alias == normalized_target or
                    alias in normalized_target or
                    normalized_target in alias
                    for alias in device.aliases
                )
            ),
            key=lambda device: max(len(alias) for alias in device.aliases),
            reverse=True,
        )
        return candidates[0] if candidates else None

    def _build_smartthings_command(
        self,
        device: SmartHomeDevice,
        request: SmartHomeRequest,
    ) -> tuple[dict | None, str | None]:
        if device.kind == "switch" and request.action in {"on", "off"}:
            return (
                self._smartthings_command_body(
                    device,
                    capability="switch",
                    command=request.action,
                ),
                f"I turned {'on' if request.action == 'on' else 'off'} {device.name}.",
            )

        if device.kind == "dimmer":
            if request.action in {"on", "off"}:
                return (
                    self._smartthings_command_body(
                        device,
                        capability="switch",
                        command=request.action,
                    ),
                    f"I turned {request.action} {device.name}.",
                )
            if request.action in {"set_level", "set_value"} and request.value is not None:
                level = max(0, min(request.value, 100))
                return (
                    self._smartthings_command_body(
                        device,
                        capability="switchLevel",
                        command="setLevel",
                        arguments=[level],
                    ),
                    f"I set {device.name} to {level}%.",
                )

        if device.kind == "lock" and request.action in {"lock", "unlock"}:
            return (
                self._smartthings_command_body(
                    device,
                    capability="lock",
                    command=request.action,
                ),
                f"I {'locked' if request.action == 'lock' else 'unlocked'} {device.name}.",
            )

        if device.kind == "door" and request.action in {"open", "close"}:
            return (
                self._smartthings_command_body(
                    device,
                    capability="doorControl",
                    command=request.action,
                ),
                f"I {'opened' if request.action == 'open' else 'closed'} {device.name}.",
            )

        if device.kind == "thermostat_heat" and request.action == "set_value" and request.value is not None:
            value = max(40, min(request.value, 95))
            return (
                self._smartthings_command_body(
                    device,
                    capability="thermostatHeatingSetpoint",
                    command="setHeatingSetpoint",
                    arguments=[value],
                ),
                f"I set {device.name} to {value} degrees.",
            )

        if device.kind == "thermostat_cool" and request.action == "set_value" and request.value is not None:
            value = max(55, min(request.value, 95))
            return (
                self._smartthings_command_body(
                    device,
                    capability="thermostatCoolingSetpoint",
                    command="setCoolingSetpoint",
                    arguments=[value],
                ),
                f"I set {device.name} to {value} degrees.",
            )

        return None, None

    def _smartthings_command_body(
        self,
        device: SmartHomeDevice,
        *,
        capability: str,
        command: str,
        arguments: list[int] | None = None,
    ) -> dict:
        entry = {
            "component": device.component,
            "capability": capability,
            "command": command,
        }
        if arguments:
            entry["arguments"] = arguments
        return {"commands": [entry]}

    async def _smartthings_send_command(self, device_id: str, payload: dict) -> None:
        headers = {
            "Authorization": f"Bearer {settings.SMARTTHINGS_PAT}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"https://api.smartthings.com/v1/devices/{device_id}/commands",
                headers=headers,
                json=payload,
            )

        if response.status_code >= 400:
            raise ValueError(
                f"Smart-home request failed ({response.status_code}): {response.text}"
            )

    def _normalize_smart_home_alias(self, value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower())

    def _normalize_smart_home_target(self, value: str) -> str:
        cleaned = self._normalize_smart_home_alias(value)
        cleaned = re.sub(r"^(?:the|my|a|an)\s+", "", cleaned)
        cleaned = re.sub(r"\bplease\b", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    async def _search_web(self, query: str) -> list[WebSearchResult]:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                headers={"User-Agent": "Orty-AIService"},
            )

        if response.status_code != 200:
            raise ValueError(f"Web search returned status {response.status_code}.")

        return self._parse_web_results(response.text)

    def _parse_web_results(self, html: str) -> list[WebSearchResult]:
        results: list[WebSearchResult] = []
        for block in RESULT_BLOCK_SPLIT_PATTERN.split(html):
            if 'class="result__a"' not in block:
                continue

            link_match = RESULT_LINK_PATTERN.search(block)
            if link_match is None:
                continue

            snippet_match = RESULT_SNIPPET_PATTERN.search(block)
            title = self._clean_html_fragment(link_match.group("title"))
            url = unescape(link_match.group("url")).strip()
            snippet = self._clean_html_fragment(
                snippet_match.group("snippet") if snippet_match is not None else ""
            )
            if not title or not url:
                continue

            results.append(WebSearchResult(title=title, url=url, snippet=snippet))
            if len(results) >= SEARCH_RESULT_LIMIT:
                break

        return results

    def _select_best_web_result(
        self,
        query: str,
        results: list[WebSearchResult]
    ) -> WebSearchResult:
        normalized_query = query.lower()

        def score(result: WebSearchResult) -> tuple[int, int]:
            haystack = f"{result.title} {result.snippet}".lower()
            points = 0
            if TIME_LIKE_PATTERN.search(haystack):
                points += 4
            if HOURS_HINT_PATTERN.search(haystack):
                points += 2
            if "store locator" in haystack:
                points -= 1
            query_term_hits = sum(1 for term in normalized_query.split() if term and term in haystack)
            return points, query_term_hits

        return max(results, key=score)

    def _clean_html_fragment(self, raw: str) -> str:
        text = TAG_PATTERN.sub(" ", raw)
        text = unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    def _truncate_text(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."
