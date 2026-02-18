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


### Fixed
- Re-checked GitHub push readiness on `dev`: configured `origin` to `https://github.com/ortluk-hub/Orty.git`, reran unit tests (`9 passed`), and retried `git push -u origin dev`; push is still blocked in this runtime because no interactive HTTPS username/PAT is available.
- Tried reconfiguring `origin` and pushing `dev` via both HTTPS and SSH; local tests pass, but this runtime cannot reach/authenticate GitHub (`could not read Username` over HTTPS, `port 22: Network is unreachable` over SSH).
- Configured `origin` remote to `https://github.com/ortluk-hub/Orty.git`, verified local sanity checks (`pytest -q`: 9 passed), and attempted `git push -u origin dev`; push is currently blocked in this environment because GitHub HTTPS credentials are unavailable.
- Re-ran full unit test suite after SQLite memory + Ollama integration verification; all tests pass as expected.
- Added unit tests for health and chat endpoint behavior (auth required, auth rejection, and no-API-key fallback) so roadmap/documentation changes are validated by executable checks.

### Documentation
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
