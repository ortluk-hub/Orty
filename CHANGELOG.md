## Unreleased

### Added
- Added a new `codey` supervisor bot type that drafts a coding-agent architecture plan with intent-resolver routing, mode-scoped system prompts, cloud/local model fallback strategy, Docker sandbox policy, and restricted network guidance.
- Refined the Android thin client UI with a polished command-centric experience, including a dedicated Command Center route and command modes for chat, task scheduling, reminders, alarms, and timers.
- Added assistant command API plumbing for `/assistant/{command}` so major assistant actions can be routed to native integrations through backend bridges.
- Added pluggable voice interfaces (`VoiceRecognitionEngine`, `TextToSpeechEngine`) with default implementations and Android TTS integration for spoken assistant responses.

- Added a lightweight Android thin-client project (`android-thin-client`) with Jetpack Compose chat/settings UI, MVVM state management, Retrofit/OkHttp networking, and a unit-tested repository contract for Orty LAN `/chat` integrations.

- Added an `automation_extensions` supervisor bot type that emits integration-target execution plans (GitHub/Slack/Notion defaults), prioritizes targets found in conversation memory, and marks resulting plans for human-reviewed implementation.
- Added unit and API tests covering automation extension target normalization, planning events, and supervisor execution flow.

### Changed
- Refined the `codey` architecture payload with an explicit intent-resolver system prompt, stricter sandbox internet-policy fields, and concrete implementation notes for containerized tooling + Alembic-backed memory traces.
- Added `/chat` conversation controls: `history_limit` (bounded 1-50), `reset_conversation`, and `persist` flags, and now return `used_history` in `ChatResponse` for observability.
- Enforced safer tool contracts by rejecting oversized `/tool` input payloads (>2000 chars) and requiring strict `owner/repo` format for GitHub helper tools.
- Switched the default `LLM_PROVIDER` from `openai` to `ollama` so local models are used by default unless overridden by environment configuration.
- Updated README environment examples to reflect Ollama as the default provider and OpenAI as an optional override.
- Added a root-path router redirect from `GET /` to `GET /ui` to prevent Not Found responses when opening the server base URL in browsers or proxies.
- Added an explicit `GET /ui/` route so trailing-slash UI requests are served directly without framework redirect hops.

### Fixed
- Removed `android-thin-client/gradle/wrapper/gradle-wrapper.jar` from version control to keep PRs free of binary artifacts.
- Fixed automation extension target normalization to treat scalar `integration_targets` strings as a single target instead of iterating character-by-character.
- Guarded supervisor bot config parsing for `history_limit`/`max_proposals` with safe positive-int fallbacks so `null` or invalid values no longer crash planning before events are emitted.
- Added test coverage for new conversation controls and safer tool contracts to prevent regressions while advancing the next roadmap milestone.
- Corrected UI routing wiring so both `GET /ui` and a root access flow (`GET /` -> `/ui`) consistently serve the web UI entrypoint.
- Fixed environment loading so Orty reads `.env` from the repository root reliably and applies it with override semantics, preventing inherited host variables from forcing `openai` when `.env` sets `LLM_PROVIDER=ollama`.

# Changelog

All notable changes to Orty will be documented in this file.

## [Unreleased]

### Added
- Added a `code_review` supervisor bot type that clones a target repository, reads optional chat memory context, and emits roadmap-aligned change proposals with explicit `human_review_required=true` enforcement for PR gating before merge.
- Introduced Heavy-Orty supervisor foundation with `/v1` APIs for client registration/authentication and bot lifecycle management (create/start/stop/pause/status/events), while preserving backward-compatible `/health` and `/chat` behavior.
- Added SQLite-backed supervisor persistence for `clients`, `bots`, and `bot_events` with safe startup initialization, ownership/event indexes, token hashing, and ISO-8601 UTC timestamps.
- Added a supervisor service layer with bot registry/state-transition checks, asyncio in-process bot runner orchestration, and a sample `heartbeat` bot type that emits periodic heartbeat audit events.
- Added new API routing structure under `service/api/routes` plus dependency/auth wiring for admin secret auth and client-scoped token auth.
- Added unit tests covering client token verification, bot lifecycle events (STARTED/HEARTBEAT/STOPPED), ownership-based authorization scoping, and v0.1 endpoint compatibility smoke checks.

### Added
- Added GitHub repository helper tools in `AIService`: `/tool gh_repo <owner/repo>` for repo metadata, `/tool gh_tree <owner/repo> [path]` for directory listings, and `/tool gh_file <owner/repo> <path> [ref]` for reading UTF-8 text files via GitHub's contents API.
- Added unit tests for GitHub helper tools and updated unknown-tool messaging coverage to include the new `gh_*` tool names.
- Added filesystem tools to `AIService` for local access: `/tool fs_pwd` (current working directory), `/tool fs_list [path]` (directory listing), and `/tool fs_read <path>` (UTF-8 file read).
- Added unit tests covering filesystem tool behavior and updated unknown-tool messaging to include newly available filesystem tools.
- Improved SQLite wiring in `MemoryStore` with WAL mode, configurable connection timeout, and a `(conversation_id, id)` index for faster history reads under concurrent usage.
- Added a unit test asserting SQLite index creation for memory queries.
- Added a Mermaid-based project architecture diagram to README showing client/API/security, AI provider routing, tool execution, and SQLite memory flow.
- Added initial built-in tool execution path in `AIService` via `/tool <name> [input]`, with default `echo` and `utc_time` tools plus runtime tool registration support.
- Added unit tests covering tool execution, UTC tool output shape, and unknown-tool error messaging.
- Added explicit roadmap position summary to clarify current phase, completed core foundations, and next milestone focus.
- Added SQLite-backed memory persistence for chat history, including generated/reused conversation IDs.
- Added Ollama provider support with configurable base URL and model via environment variables.
- Added unit tests for memory store behavior and provider selection routing.
- Refined LLM abstraction in `AIService` with a provider registry, explicit unsupported-provider messaging, and runtime registration support for additional providers.


### Changed
- Made the web UI route resilient for both `GET /ui` and `GET /ui/` to avoid 404/redirect edge cases across different clients and proxies.
- Moved the built-in web UI endpoint from `/` to `/ui` to make the UI route explicit and avoid ambiguity with API-first behavior.
- Updated API tests and README documentation to use `GET /ui` for the web interface.

### Fixed
- Re-checked GitHub push readiness on `dev`: configured `origin` to `https://github.com/ortluk-hub/Orty.git`, reran unit tests (`9 passed`), and retried `git push -u origin dev`; push is still blocked in this runtime because no interactive HTTPS username/PAT is available.
- Tried reconfiguring `origin` and pushing `dev` via both HTTPS and SSH; local tests pass, but this runtime cannot reach/authenticate GitHub (`could not read Username` over HTTPS, `port 22: Network is unreachable` over SSH).
- Configured `origin` remote to `https://github.com/ortluk-hub/Orty.git`, verified local sanity checks (`pytest -q`: 9 passed), and attempted `git push -u origin dev`; push is currently blocked in this environment because GitHub HTTPS credentials are unavailable.
- Re-ran full unit test suite after SQLite memory + Ollama integration verification; all tests pass as expected.
- Added unit tests for health and chat endpoint behavior (auth required, auth rejection, and no-API-key fallback) so roadmap/documentation changes are validated by executable checks.

### Documentation
- Added and documented a simple built-in web UI at `/` for manual chat/conversation testing, while keeping Orty API-first for programmatic integrations.
- Added README instructions for running Orty and Ollama in separate Docker containers on the same host, including LAN client access patterns.
- Added a README version badge (`v0.1.0-alpha`) for quick project status visibility at a glance.
- Updated README roadmap/status sections to reflect completed LLM abstraction + built-in tool milestones and to shift near-term planning toward conversation controls, safer tool contracts, and automation extensions.
- Removed extensive GitHub push/auth/troubleshooting instructions from `README.md`; development workflow docs now stay focused on local branch/merge flow.
- Clarified in `README.md` that `git push` from non-interactive environments requires preconfigured credentials (credential helper, `GH_TOKEN`/PAT wiring, or SSH agent), otherwise Git cannot prompt for a username/password.
- Added a non-interactive HTTPS push example that reads the username from `GITHUB-USER` (or `GITHUB_USER`) and uses `GITHUB_TOKEN` for PAT-based authentication.
- Updated HTTPS credential docs to also support `GITHUB-PAT`/`GITHUB_PAT` and made the non-interactive push example resolve both hyphenated and underscored env var names.
- Corrected credential env-var guidance to recommend Bash-exportable names (`GITHUB_USER`, `GITHUB_PAT`) and treat hyphenated names as runtime-injected fallback only.
- Added a credential-visibility check to README (`env | rg ...`) so non-interactive shells can confirm whether GitHub env vars are actually injected before retrying `git push`.
- Added an “Explain like I'm 5” summary in README for GitHub push/auth flow (commit vs push and why `GITHUB_USER` + `GITHUB_PAT`/`GITHUB_TOKEN` are required).
- Added a new roadmap subsection in README that answers “what's next” with near-term priorities: LLM abstraction refinement, tool execution support, and conversation/memory evolution.
- Updated GitHub HTTPS credential guidance to use the repo owner username (`ortluk-hub`) and aligned SSH key example email to `ortluk@gmail.com`.
- Documented and validated the SSH key generation flow for GitHub auth (`ssh-keygen -t ed25519`) and public-key export (`cat ~/.ssh/id_ed25519.pub`) for developer setup.
- Added SSH-first GitHub push instructions (remote switch, key creation, and verification) to bypass HTTPS proxy tunnel failures.
- Expanded GitHub 403 guidance with a prevention checklist (NO_PROXY retry, allowlist targets, SSH fallback, and auth checks).
- Added README troubleshooting steps for GitHub proxy tunnel errors (`CONNECT tunnel failed, response 403`).
- Added explicit instructions for configuring the GitHub `origin` remote before pushing `dev`.
- Clarified which GitHub credentials are required to push after configuring `origin` (HTTPS PAT vs SSH key auth).
- Clarified development workflow: `git commit` is local, and `git push origin dev` is required to publish commits on GitHub.
- Added initial changelog file for tracking project evolution.


### Changed
- Refactored authentication to prioritize registered client credentials, while preserving `x-orty-secret` as an admin/root fallback that resolves to a primary client identity.
- Added per-client preferences support and primary-client metadata in client APIs/storage.
- Scoped chat-memory persistence and retrieval by client identity to keep conversation state isolated across clients.
- Added `/ui/chat` and updated the web UI to operate as the primary root-user chat interface without manual secret entry.


### Migration Notes
- SQLite schema migration is automatic at startup: `messages.client_id`, `clients.preferences_json`, and `clients.is_primary` are added if missing.

### Rollback
- Revert commit `7b4189d` and this follow-up commit to restore the previous auth/UI behavior.

### Changed
- Restricted `POST /v1/clients` to admin (`x-orty-secret`) to keep client provisioning under primary/root authority.
