from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
import base64
from dataclasses import dataclass
from html import unescape
import inspect
import json
import logging
from pathlib import Path
import re
import time
from typing import TypedDict

import httpx

# Import Vertex AI SDK
try:
    import google.auth as google_auth
    from google.cloud import aiplatform
except ImportError:
    aiplatform = None
    google_auth = None

from service.config import settings

logger = logging.getLogger("uvicorn.error")

GenerateFn = Callable[..., Awaitable[str]]
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


@dataclass(frozen=True)
class SmartHomeGroup:
    name: str
    aliases: tuple[str, ...]
    members: tuple[str, ...]


class GenerationResult(TypedDict):
    reply: str
    provider: str
    handled_by: str
    fallback_used: bool
    fallback_provider: str | None


@dataclass(frozen=True)
class ChatRequestContext:
    channel: str = "api"
    conversation_id: str | None = None
    auth_method: str | None = None
    current_client: dict | None = None
    requested_client_name: str | None = None
    assistant_name: str | None = None
    personality_preset: str | None = None
    client_system_prompt: str | None = None


class AIService:
    def __init__(
        self,
        *,
        clients_repo=None,
        bots_repo=None,
        bug_reports_repo=None,
        memory_records_repo=None,
        codey_client=None,
        codey_bug_processor=None,
    ):
        self.clients_repo = clients_repo
        self.bots_repo = bots_repo
        self.bug_reports_repo = bug_reports_repo
        self.memory_records_repo = memory_records_repo
        self.codey_client = codey_client
        self.codey_bug_processor = codey_bug_processor
        self._providers: dict[str, GenerateFn] = {
            "openai": self._generate_openai,
            "ollama": self._generate_ollama,
            "ollama_cloud": self._generate_ollama_cloud,
            # Register Vertex AI provider
            "vertex_ai": self._generate_vertex_ai,
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
            "clients_overview": self._tool_clients_overview,
            "bots_overview": self._tool_bots_overview,
            "memory_overview": self._tool_memory_overview,
            "codey_overview": self._tool_codey_overview,
            "system_overview": self._tool_system_overview,
        }

    def register_provider(self, name: str, generator: GenerateFn) -> None:
        self._providers[name.lower()] = generator

    def register_tool(self, name: str, tool: ToolFn) -> None:
        self._tools[name.lower()] = tool

    async def generate(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
        request_context: ChatRequestContext | None = None,
    ) -> str:
        result = await self.generate_with_meta(message, history=history, request_context=request_context)
        return result["reply"]

    async def generate_with_meta(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
        request_context: ChatRequestContext | None = None,
    ) -> GenerationResult:
        request_start = time.perf_counter()
        provider = settings.LLM_PROVIDER.lower()
        history = history or []
        system_prompt = self._build_system_prompt(request_context=request_context)

        tool_result = await self._maybe_execute_tool(message, request_context=request_context)
        if tool_result is not None:
            self._log_generation_summary(
                message=message,
                provider="tool",
                handled_by="tool",
                fallback_used=False,
                request_start=request_start,
            )
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
            self._log_generation_summary(
                message=message,
                provider=provider,
                handled_by="unsupported-provider",
                fallback_used=False,
                request_start=request_start,
            )
            return {
                "reply": f"Unsupported LLM_PROVIDER '{provider}'. Available providers: {available}.",
                "provider": provider,
                "handled_by": "unsupported-provider",
                "fallback_used": False,
                "fallback_provider": None,
            }

        fallback_provider = settings.CLOUD_FALLBACK_PROVIDER.lower()
        fallback_generator = self._providers.get(fallback_provider) if fallback_provider else None
        race_result = await self._maybe_generate_with_race(
            provider=provider,
            generator=generator,
            fallback_provider=fallback_provider,
            fallback_generator=fallback_generator,
            message=message,
            history=history,
            system_prompt=system_prompt,
        )
        if race_result is not None:
            self._log_generation_summary(
                message=message,
                provider=race_result["provider"],
                handled_by=race_result["handled_by"],
                fallback_used=race_result["fallback_used"],
                request_start=request_start,
            )
            return race_result

        primary_reply, _ = await self._timed_provider_call(
            provider=provider,
            generator=generator,
            message=message,
            history=history,
            system_prompt=system_prompt,
            phase="primary",
        )
        if not self._should_attempt_cloud_fallback(provider, primary_reply):
            self._log_generation_summary(
                message=message,
                provider=provider,
                handled_by=self._handled_by_for_provider(provider, fallback_used=False),
                fallback_used=False,
                request_start=request_start,
            )
            return {
                "reply": primary_reply,
                "provider": provider,
                "handled_by": self._handled_by_for_provider(provider, fallback_used=False),
                "fallback_used": False,
                "fallback_provider": None,
            }

        if fallback_generator is None:
            self._log_generation_summary(
                message=message,
                provider=provider,
                handled_by=self._handled_by_for_provider(provider, fallback_used=False),
                fallback_used=False,
                request_start=request_start,
            )
            return {
                "reply": primary_reply,
                "provider": provider,
                "handled_by": self._handled_by_for_provider(provider, fallback_used=False),
                "fallback_used": False,
                "fallback_provider": None,
            }

        fallback_reply, _ = await self._timed_provider_call(
            provider=fallback_provider,
            generator=fallback_generator,
            message=message,
            history=history,
            system_prompt=system_prompt,
            phase="fallback",
        )
        if self._is_provider_error(fallback_provider, fallback_reply):
            reply_message = (
                primary_reply
                + "\n\n"
                + f"Cloud fallback ({fallback_provider}) also failed: {fallback_reply}"
            )
            self._log_generation_summary(
                message=message,
                provider=provider,
                handled_by=self._handled_by_for_provider(provider, fallback_used=False),
                fallback_used=False,
                request_start=request_start,
            )
            return {
                "reply": reply_message,
                "provider": provider,
                "handled_by": self._handled_by_for_provider(provider, fallback_used=False),
                "fallback_used": False,
                "fallback_provider": fallback_provider,
            }
        self._log_generation_summary(
            message=message,
            provider=fallback_provider,
            handled_by=self._handled_by_for_provider(fallback_provider, fallback_used=True),
            fallback_used=True,
            request_start=request_start,
        )
        return {
            "reply": fallback_reply,
            "provider": fallback_provider,
            "handled_by": self._handled_by_for_provider(fallback_provider, fallback_used=True),
            "fallback_used": True,
            "fallback_provider": fallback_provider,
        }

    async def _maybe_generate_with_race(
        self,
        *,
        provider: str,
        generator: GenerateFn,
        fallback_provider: str,
        fallback_generator: GenerateFn | None,
        message: str,
        history: list[dict[str, str]],
        system_prompt: str,
    ) -> GenerationResult | None:
        if not settings.ENABLE_PARALLEL_PROVIDER_RACE:
            return None
        if not settings.ENABLE_CLOUD_FALLBACK:
            return None
        if not fallback_provider or fallback_provider == provider.lower():
            return None
        if fallback_generator is None:
            return None

        race_start = time.perf_counter()
        logger.info(
            "provider_race_started primary=%s fallback=%s message_chars=%d history=%d",
            provider,
            fallback_provider,
            len(message),
            len(history),
        )

        primary_task = asyncio.create_task(
            self._timed_provider_call(
                provider=provider,
                generator=generator,
                message=message,
                history=history,
                system_prompt=system_prompt,
                phase="race_primary",
            )
        )
        fallback_task = asyncio.create_task(
            self._timed_provider_call(
                provider=fallback_provider,
                generator=fallback_generator,
                message=message,
                history=history,
                system_prompt=system_prompt,
                phase="race_fallback",
            )
        )
        task_meta = {
            primary_task: (provider, False),
            fallback_task: (fallback_provider, True),
        }
        replies: dict[tuple[str, bool], tuple[str, int]] = {}

        try:
            pending: set[asyncio.Task[tuple[str, int]]] = {primary_task, fallback_task}
            while pending:
                done, pending = await asyncio.wait(
                    pending,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    task_provider, used_fallback = task_meta[task]
                    reply, elapsed_ms = await task
                    replies[(task_provider, used_fallback)] = (reply, elapsed_ms)
                    if not self._is_provider_error(task_provider, reply):
                        for other in pending:
                            other.cancel()
                        await asyncio.gather(*pending, return_exceptions=True)
                        logger.info(
                            "provider_race_winner winner=%s fallback_used=%s elapsed_ms=%d total_race_ms=%d",
                            task_provider,
                            used_fallback,
                            elapsed_ms,
                            self._elapsed_ms(race_start),
                        )
                        return {
                            "reply": reply,
                            "provider": task_provider,
                            "handled_by": self._handled_by_for_provider(
                                task_provider,
                                fallback_used=used_fallback,
                            ),
                            "fallback_used": used_fallback,
                            "fallback_provider": fallback_provider if used_fallback else None,
                        }

            primary_result = replies.get((provider, False))
            fallback_result = replies.get((fallback_provider, True))
            if primary_result is None or fallback_result is None:
                return None
            primary_reply, primary_elapsed_ms = primary_result
            fallback_reply, fallback_elapsed_ms = fallback_result

            logger.info(
                "provider_race_no_winner primary=%s primary_ms=%d fallback=%s fallback_ms=%d total_race_ms=%d",
                provider,
                primary_elapsed_ms,
                fallback_provider,
                fallback_elapsed_ms,
                self._elapsed_ms(race_start),
            )

            return {
                "reply": (
                    primary_reply
                    + "\n\n"
                    + f"Cloud fallback ({fallback_provider}) also failed: {fallback_reply}"
                ),
                "provider": provider,
                "handled_by": self._handled_by_for_provider(provider, fallback_used=False),
                "fallback_used": False,
                "fallback_provider": fallback_provider,
            }
        finally:
            for task in (primary_task, fallback_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(primary_task, fallback_task, return_exceptions=True)

    def _is_provider_error(self, provider: str, reply: str) -> bool:
        normalized = provider.lower()
        if normalized in {"ollama", "ollama_cloud"}:
            return reply.startswith("Ollama is not reachable.") or reply.startswith("Ollama error:")
        if normalized == "openai":
            return reply == "OPENAI_API_KEY not configured." or reply.startswith("OpenAI error:")
        if normalized == "vertex_ai":
            return reply.startswith("Vertex AI not configured") or reply.startswith("Vertex AI error:")
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
        if normalized == "vertex_ai":
            return "vertex_ai_primary"
        return normalized

    async def _timed_provider_call(
        self,
        *,
        provider: str,
        generator: GenerateFn,
        message: str,
        history: list[dict[str, str]],
        system_prompt: str,
        phase: str,
    ) -> tuple[str, int]:
        start = time.perf_counter()
        logger.info(
            "provider_call_started provider=%s phase=%s message_chars=%d history=%d",
            provider,
            phase,
            len(message),
            len(history),
        )
        try:
            reply = await self._invoke_generator(
                generator,
                message=message,
                history=history,
                system_prompt=system_prompt,
            )
        except Exception:
            logger.exception(
                "provider_call_exception provider=%s phase=%s elapsed_ms=%d",
                provider,
                phase,
                self._elapsed_ms(start),
            )
            raise

        elapsed_ms = self._elapsed_ms(start)
        logger.info(
            "provider_call_completed provider=%s phase=%s elapsed_ms=%d outcome=%s",
            provider,
            phase,
            elapsed_ms,
            "error_reply" if self._is_provider_error(provider, reply) else "success_reply",
        )
        return reply, elapsed_ms

    async def _invoke_generator(
        self,
        generator: GenerateFn,
        *,
        message: str,
        history: list[dict[str, str]],
        system_prompt: str,
    ) -> str:
        try:
            return await generator(message, history, system_prompt)
        except TypeError:
            return await generator(message, history)

    def _log_generation_summary(
        self,
        *,
        message: str,
        provider: str,
        handled_by: str,
        fallback_used: bool,
        request_start: float,
    ) -> None:
        logger.info(
            "generation_completed provider=%s handled_by=%s fallback_used=%s total_ms=%d message_chars=%d",
            provider,
            handled_by,
            fallback_used,
            self._elapsed_ms(request_start),
            len(message),
        )

    def _elapsed_ms(self, start: float) -> int:
        return int((time.perf_counter() - start) * 1000)

    def _build_system_prompt(self, request_context: ChatRequestContext | None = None) -> str:
        channel = (request_context.channel if request_context else "api").strip() or "api"
        current_client = request_context.current_client if request_context else {}
        presented_name = ((request_context.assistant_name if request_context else "") or "").strip()
        requested_client = ((request_context.requested_client_name if request_context else "") or "").strip()

        lines: list[str] = [
            "Identity:",
            "- You are Orty, the server system and coordination layer behind assistant clients.",
            "- Your identity is the server and supervisor itself, not whichever language model is currently generating text.",
            "- Treat the active language model as one of your faculties for reasoning and language generation.",
            "- You are aware of your managed memory systems, client/userbase, bot registry, and Codey maintenance pipeline.",
            "",
            "Core role:",
            "- Act like the assistant of assistants: grounded, operationally aware, and honest about what the server can actually inspect or do.",
            "- When discussing the system, speak from the perspective of Orty the server, not as a generic chatbot model.",
        ]

        if channel == "orty_web_ui":
            lines.extend(
                [
                    "",
                    "Channel contract:",
                    "- This is the Orty web UI.",
                    "- Speak directly as Orty here.",
                    "- It is appropriate to discuss your system state, memory, managed clients, bots, and Codey coordination explicitly.",
                ]
            )
        elif request_context and request_context.client_system_prompt:
            lines.extend(
                [
                    "",
                    "Client response contract:",
                    "- This request came through a managed client.",
                    "- Remain aware that you are Orty internally, but shape the outward response to the client contract below.",
                    f"- Requested client surface: {requested_client or channel}.",
                ]
            )
            if presented_name:
                lines.append(f"- Presented assistant name for this client: {presented_name}.")
            if request_context.personality_preset:
                lines.append(f"- Requested client personality preset: {request_context.personality_preset}.")
            lines.append("- Client contract follows verbatim:")
            lines.append(request_context.client_system_prompt.strip())

        lines.extend(
            [
                "",
                "Live server awareness:",
                *self._build_runtime_awareness_lines(request_context),
                "",
                "Faculties and tool set:",
                "- Language generation: local/cloud model providers are faculties, not identity.",
                "- Memory database: message history plus structured memory records and summaries.",
                "- Userbase management: client registry, auth state, promotion/admin awareness.",
                "- Bot management: managed bots with owner, type, and status awareness.",
                "- Code maintenance: bug reports and Codey task-management pipeline when configured.",
                "- Explicit slash tools available: /tool system_overview, /tool clients_overview, /tool bots_overview, /tool memory_overview, /tool codey_overview, plus existing filesystem, GitHub, smart-home, web search, and time tools.",
                "",
                "Response rules:",
                "- Never claim direct code execution, task approval, client mutation, or bot changes unless a real action path exists and was actually used.",
                "- If asked about system state, answer from the live server awareness block first.",
                "- If context is incomplete, say what you do know and what system surface you would inspect next.",
                "- Keep responses concise by default, but be concrete and operationally literate.",
            ]
        )

        return "\n".join(lines).strip()

    def _build_runtime_awareness_lines(
        self,
        request_context: ChatRequestContext | None,
    ) -> list[str]:
        lines: list[str] = []
        current_client = request_context.current_client if request_context else None
        if current_client:
            client_name = current_client.get("name") or "unnamed"
            lines.append(
                f"- Current authenticated client: {client_name} ({current_client.get('client_id', 'unknown')})."
            )
            if request_context and request_context.auth_method:
                lines.append(f"- Auth path for this request: {request_context.auth_method}.")

        if self.clients_repo is not None:
            try:
                clients = self.clients_repo.list_clients()
                admins = self.clients_repo.get_admin_clients()
                active_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
                stale_clients = 0
                active_clients = 0
                for client in clients:
                    last_seen = client.get("last_seen_at")
                    if not last_seen:
                        stale_clients += 1
                        continue
                    try:
                        seen_at = datetime.fromisoformat(last_seen)
                    except ValueError:
                        stale_clients += 1
                        continue
                    if seen_at.tzinfo is None:
                        seen_at = seen_at.replace(tzinfo=timezone.utc)
                    if seen_at >= active_cutoff:
                        active_clients += 1
                    else:
                        stale_clients += 1
                sample_clients = ", ".join(
                    (client.get("name") or client["client_id"][:8]) for client in clients[:4]
                ) or "none"
                lines.append(
                    f"- Managed clients: {len(clients)} total, {active_clients} active in the last 30 days, {stale_clients} stale."
                )
                lines.append(f"- Client sample: {sample_clients}.")
                lines.append(f"- Admin-capable clients: {len(admins)}.")
            except Exception as exc:
                lines.append(f"- Client registry awareness unavailable: {exc}.")

        if self.bots_repo is not None:
            try:
                bots = self.bots_repo.list_bots(limit=20)
                status_counts: dict[str, int] = {}
                for bot in bots:
                    status = bot.get("status") or "unknown"
                    status_counts[status] = status_counts.get(status, 0) + 1
                status_summary = ", ".join(
                    f"{status}={count}" for status, count in sorted(status_counts.items())
                ) or "none"
                lines.append(f"- Managed bots: {len(bots)} known ({status_summary}).")
            except Exception as exc:
                lines.append(f"- Bot registry awareness unavailable: {exc}.")

        if self.memory_records_repo is not None and current_client:
            try:
                records = self.memory_records_repo.list_records(
                    client_id=current_client["client_id"],
                    limit=5,
                )
                lines.append(
                    f"- Structured memory records for current client: {len(records)} recent items available."
                )
            except Exception as exc:
                lines.append(f"- Structured memory overview unavailable: {exc}.")

        if self.codey_bug_processor is not None or self.codey_client is not None or self.bug_reports_repo is not None:
            try:
                report_count = len(self.bug_reports_repo.list_reports(limit=20)) if self.bug_reports_repo is not None else 0
                lines.append(
                    f"- Code maintenance pipeline: {'configured' if self.codey_client is not None else 'not configured'}, {report_count} recent bug reports tracked."
                )
            except Exception as exc:
                lines.append(f"- Code maintenance overview unavailable: {exc}.")

        if not lines:
            lines.append("- Live server-awareness surfaces are not configured in this process.")
        return lines

    async def _generate_openai(
        self,
        message: str,
        history: list[dict[str, str]],
        system_prompt: str | None = None,
    ) -> str:
        if not settings.OPENAI_API_KEY:
            return "OPENAI_API_KEY not configured."

        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": settings.OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt or self._build_system_prompt()},
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

    async def _generate_ollama(
        self,
        message: str,
        history: list[dict[str, str]],
        system_prompt: str | None = None,
    ) -> str:
        return await self._generate_ollama_with_model(
            settings.OLLAMA_MODEL,
            message,
            history,
            system_prompt=system_prompt,
        )

    async def _generate_ollama_cloud(
        self,
        message: str,
        history: list[dict[str, str]],
        system_prompt: str | None = None,
    ) -> str:
        model = settings.OLLAMA_CLOUD_FALLBACK_MODEL.strip()
        if not model:
            return "Ollama error: cloud fallback model not configured."
        return await self._generate_ollama_with_model(
            model,
            message,
            history,
            system_prompt=system_prompt,
        )

    async def _generate_ollama_with_model(
        self,
        model: str,
        message: str,
        history: list[dict[str, str]],
        *,
        system_prompt: str | None = None,
    ) -> str:
        payload = {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt or self._build_system_prompt()},
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

    async def _generate_vertex_ai(
        self,
        message: str,
        history: list[dict[str, str]],
        system_prompt: str | None = None,
    ) -> str:
        if aiplatform is None or google_auth is None:
            return "Vertex AI SDK not found. Please install google-cloud-aiplatform."
        
        if not (settings.VERTEX_AI_PROJECT_ID and settings.VERTEX_AI_LOCATION and settings.VERTEX_AI_MODEL_ID):
            return "Vertex AI not configured. Ensure VERTEX_AI_PROJECT_ID, VERTEX_AI_LOCATION, and VERTEX_AI_MODEL_ID are set."

        try:
            # Attempt to authenticate using Application Default Credentials (ADC)
            # or a service account key if VERTEX_AI_CREDENTIALS_PATH is provided.
            if settings.VERTEX_AI_CREDENTIALS_PATH:
                credentials, project = google_auth.load_credentials_from_file(settings.VERTEX_AI_CREDENTIALS_PATH)
            else:
                credentials, project = google_auth.default()

            aiplatform.init(project=settings.VERTEX_AI_PROJECT_ID, location=settings.VERTEX_AI_LOCATION, credentials=credentials)

            # Vertex AI expects different model IDs and endpoint structures.
            # For Generative AI models (like Gemini), you typically use the `VertexModel` class.
            # The exact model ID might vary (e.g., "gemini-1.5-pro-preview-0514").
            # The model needs to be deployed to an endpoint, or you use a pre-trained model.
            # Assuming a deployed model for now. If it's a public model, the process might differ.

            # For public models like Gemini, you might use VertexAI endpoint directly, not a deployed model.
            # Example for Gemini Pro:
            # from vertexai.generative_models import GenerativeModel, Part
            # model = GenerativeModel("gemini-1.5-pro-preview-0514")

            # If using a deployed model:
            # model_endpoint = aiplatform.Endpoint.create(
            #     display_name=settings.VERTEX_AI_MODEL_ID.replace("_", "-"), # Use a valid display name
            #     project=settings.VERTEX_AI_PROJECT_ID,
            #     location=settings.VERTEX_AI_LOCATION,
            #     # You might need to specify the model resource name here if creating an endpoint.
            # )

            # For this example, let's assume we are interacting with a Vertex AI Model object directly
            # or a deployed endpoint. The exact SDK usage depends on how the model is provisioned in Vertex AI.
            # A common pattern for foundation models is to use vertexai.generative_models.GenerativeModel
            # which doesn't require explicit deployment for public models.

            # Check if settings.VERTEX_AI_MODEL_ID refers to a public model name or a deployed endpoint ID.
            # For now, assuming it's a public model name (like 'gemini-1.5-pro-preview-0514').
            
            # Note: The exact way to instantiate and call models in Vertex AI can be complex and depends
            # on whether it's a public foundation model or a custom-deployed model.
            # This is a placeholder implementation.

            # If using public foundation models (like Gemini):
            from vertexai.generative_models import Content, GenerativeModel, Part
            model = GenerativeModel(settings.VERTEX_AI_MODEL_ID)

            # Constructing the history for Vertex AI
            # Vertex AI's chat history format might differ slightly.
            # Typically, it involves roles like "user" and "model".
            # The system prompt might be handled differently (e.g., as part of the first user message or a separate config).
            
            # A simplified approach: prepend system prompt to user message if model supports it.
            # For Generative models, history is usually a list of 'contents' or 'parts'.
            vertex_history: list[Content] = []
            effective_system_prompt = system_prompt or self._build_system_prompt()
            if effective_system_prompt:
                vertex_history.append(
                    Content(role="user", parts=[Part.from_text(effective_system_prompt)])
                )
            for turn in history:
                role = turn["role"]
                content = turn["content"]
                if role == "system": # Handle system prompt if applicable to the model's input format
                    vertex_history.append(
                        Content(role="user", parts=[Part.from_text(content)])
                    )
                elif role == "user":
                    vertex_history.append(
                        Content(role="user", parts=[Part.from_text(content)])
                    )
                elif role == "assistant": # 'assistant' is often mapped to 'model' in other APIs
                    vertex_history.append(
                        Content(role="model", parts=[Part.from_text(content)])
                    )

            # Prepend system prompt if the model expects it as part of the input
            # Gemini often handles system instructions during model instantiation or as a separate argument.
            # For this example, we will include it in the first user message if no history, or as a separate system_instruction if available.
            # A more robust implementation would check the specific model's API.

            # Let's try a common pattern: passing history directly and the system prompt might be handled by the model.
            chat_session = model.start_chat(
                history=vertex_history or None, # Pass the constructed history
                # If the model supports system instructions directly:
                # system_instruction="You are Orty, a concise and intelligent on-device assistant.",
            )

            response = chat_session.send_message(message) # Send the current message

            # Extract the content from the response
            # The structure of the response might vary. For Gemini, it's usually response.text
            # Or response.candidates[0].content.parts[0].text
            generated_text = ""
            if response.text:
                generated_text = response.text
            else:
                # Fallback for other potential response structures
                try:
                    generated_text = response.text
                except AttributeError:
                    # Try to access parts if response.text is not directly available
                    if hasattr(response, 'candidates') and response.candidates:
                        for candidate in response.candidates:
                            if candidate.content and candidate.content.parts:
                                for part in candidate.content.parts:
                                    if part.text:
                                        generated_text += part.text
                                        break # Assuming only one text part per candidate
                                if generated_text:
                                    break
            
            if not generated_text:
                return "Vertex AI error: Failed to extract text from response."

            return generated_text

        except google_auth.exceptions.DefaultCredentialsError as e:
            return f"Vertex AI authentication error: {e}. Ensure GOOGLE_APPLICATION_CREDENTIALS is set or ADC is configured."
        except ImportError:
            return "Vertex AI SDK not found. Please install google-cloud-aiplatform."
        except Exception as e:
            return f"Vertex AI error: {e}"

    async def _maybe_execute_tool(
        self,
        message: str,
        request_context: ChatRequestContext | None = None,
    ) -> str | None:
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

    async def _tool_system_overview(self, _: str) -> str:
        return "\n".join(self._build_runtime_awareness_lines(None))

    async def _tool_clients_overview(self, _: str) -> str:
        if self.clients_repo is None:
            return "Client registry is not configured in this Orty process."
        clients = self.clients_repo.list_clients()
        admins = self.clients_repo.get_admin_clients()
        if not clients:
            return "No managed clients are currently registered."
        lines = [f"Managed clients: {len(clients)} total, {len(admins)} admin."]
        for client in clients[:8]:
            name = client.get("name") or "(unnamed)"
            lines.append(
                f"- {name} [{client['client_id'][:8]}] primary={bool(client.get('is_primary'))} admin={bool(client.get('is_admin'))} last_seen={client.get('last_seen_at') or 'never'}"
            )
        return "\n".join(lines)

    async def _tool_bots_overview(self, _: str) -> str:
        if self.bots_repo is None:
            return "Bot registry is not configured in this Orty process."
        bots = self.bots_repo.list_bots(limit=20)
        if not bots:
            return "No managed bots are currently registered."
        lines = [f"Managed bots: {len(bots)} recent entries."]
        for bot in bots[:10]:
            lines.append(
                f"- {bot['bot_type']} bot [{bot['bot_id'][:8]}] owner={bot['owner_client_id'][:8]} status={bot.get('status', 'unknown')}"
            )
        return "\n".join(lines)

    async def _tool_memory_overview(self, tool_input: str) -> str:
        if self.memory_records_repo is None or self.clients_repo is None:
            return "Structured memory overview is not configured in this Orty process."
        requested = tool_input.strip()
        target_client_id = requested or None
        if target_client_id is None:
            primary = self.clients_repo.get_primary_client()
            if primary is None:
                return "No target client available for memory overview."
            target_client_id = primary["client_id"]
        records = self.memory_records_repo.list_records(client_id=target_client_id, limit=8)
        if not records:
            return f"No active structured memory records found for client {target_client_id[:8]}."
        lines = [f"Structured memory for client {target_client_id[:8]}: {len(records)} recent records."]
        for record in records:
            summary = record.get("summary") or self._truncate_text(record.get("content", ""), 100)
            lines.append(
                f"- {record.get('memory_type', 'memory')} importance={record.get('importance', 0):.2f} pinned={bool(record.get('is_pinned'))}: {summary}"
            )
        return "\n".join(lines)

    async def _tool_codey_overview(self, _: str) -> str:
        configured = self.codey_client is not None
        if self.bug_reports_repo is None:
            return f"Codey configured={configured}. Bug-report repository is unavailable."
        reports = self.bug_reports_repo.list_reports(limit=10)
        if not reports:
            return f"Codey configured={configured}. No recent bug reports are tracked."
        lines = [f"Codey configured={configured}. Recent bug reports: {len(reports)}."]
        for report in reports[:8]:
            lines.append(
                f"- {report['title']} [{report['report_id'][:8]}] status={report.get('status', 'unknown')} codey_task={report.get('codey_task_id') or 'none'}"
            )
        return "\n".join(lines)

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

        matched_devices = self._resolve_smart_home_group_devices(parsed.target, devices)
        if not matched_devices:
            matched_devices = self._match_smart_home_devices(parsed.target, devices)
        if not matched_devices:
            return (
                f"I couldn't find a configured smart-home device matching '{parsed.target}'."
            )

        commands: list[tuple[SmartHomeDevice, dict]] = []
        for device in matched_devices:
            command_body, _ = self._build_smartthings_command(device, parsed)
            if command_body is None:
                return (
                    f"I couldn't map '{command_text}' to a supported command for {device.name}. "
                    "Check the device kind in SMARTTHINGS_DEVICE_MAP."
                )
            commands.append((device, command_body))

        if not commands:
            return (
                f"I couldn't map '{command_text}' to a supported command."
            )

        try:
            await asyncio.gather(
                *(
                    self._smartthings_send_command(device.device_id, command_body)
                    for device, command_body in commands
                )
            )
        except httpx.RequestError as exc:
            return f"Smart-home request failed: {exc}"
        except ValueError as exc:
            return str(exc)

        return self._build_group_success_reply(
            [device for device, _ in commands],
            parsed,
        )

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

    def _load_smartthings_groups(self) -> list[SmartHomeGroup]:
        raw = settings.SMARTTHINGS_GROUP_MAP.strip()
        if not raw:
            return []

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []

        if not isinstance(payload, dict):
            return []

        groups: list[SmartHomeGroup] = []
        for alias, config in payload.items():
            if not isinstance(config, dict):
                continue
            name = str(config.get("name") or alias).strip()
            members = tuple(
                self._normalize_smart_home_alias(member)
                for member in (config.get("members") or [])
                if str(member).strip()
            )
            aliases = tuple(
                {
                    self._normalize_smart_home_alias(group_alias)
                    for group_alias in [name, alias, *(config.get("aliases") or [])]
                    if str(group_alias).strip()
                }
            )
            if not name or not members or not aliases:
                continue
            groups.append(
                SmartHomeGroup(
                    name=name,
                    aliases=aliases,
                    members=members,
                )
            )
        return groups

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

    def _match_smart_home_devices(
        self,
        target: str,
        devices: list[SmartHomeDevice]
    ) -> list[SmartHomeDevice]:
        normalized_target = self._normalize_smart_home_target(target)
        if not normalized_target:
            return []

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
        if not candidates:
            return []

        exact_alias_matches = [
            device for device in candidates if normalized_target in device.aliases
        ]
        if len(exact_alias_matches) > 1:
            return exact_alias_matches
        if exact_alias_matches:
            return [exact_alias_matches[0]]

        longest_alias_length = max(len(alias) for alias in candidates[0].aliases)
        longest_matches = [
            device
            for device in candidates
            if max(len(alias) for alias in device.aliases) == longest_alias_length
        ]
        return longest_matches if len(longest_matches) > 1 else [candidates[0]]

    def _resolve_smart_home_group_devices(
        self,
        target: str,
        devices: list[SmartHomeDevice],
    ) -> list[SmartHomeDevice]:
        normalized_target = self._normalize_smart_home_target(target)
        if not normalized_target:
            return []

        groups = self._load_smartthings_groups()
        matching_groups = [
            group
            for group in groups
            if any(
                alias == normalized_target or
                alias in normalized_target or
                normalized_target in alias
                for alias in group.aliases
            )
        ]
        if not matching_groups:
            return []

        matching_groups.sort(
            key=lambda group: max(len(alias) for alias in group.aliases),
            reverse=True,
        )
        selected_group = matching_groups[0]
        members_by_alias = {
            alias: device
            for device in devices
            for alias in device.aliases
        }
        resolved_devices: list[SmartHomeDevice] = []
        seen_ids: set[str] = set()
        for member in selected_group.members:
            device = members_by_alias.get(member)
            if device is None or device.device_id in seen_ids:
                continue
            resolved_devices.append(device)
            seen_ids.add(device.device_id)
        return resolved_devices

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

    def _format_smart_home_target_names(self, devices: list[SmartHomeDevice]) -> str:
        names = [device.name for device in devices]
        if not names:
            return "those devices"
        if len(names) == 1:
            return names[0]
        if len(names) == 2:
            return f"{names[0]} and {names[1]}"
        return f"{', '.join(names[:-1])}, and {names[-1]}"

    def _build_group_success_reply(
        self,
        devices: list[SmartHomeDevice],
        request: SmartHomeRequest,
    ) -> str:
        target_names = self._format_smart_home_target_names(devices)
        if request.action in {"on", "off"}:
            return f"I turned {request.action} {target_names}."
        if request.action in {"set_level", "set_value"} and request.value is not None:
            if all(device.kind == "dimmer" for device in devices):
                return f"I set {target_names} to {request.value}%."
            return f"I set {target_names} to {request.value}."
        return f"I updated {target_names}."

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
