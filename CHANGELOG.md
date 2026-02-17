# Changelog

All notable changes to Orty will be documented in this file.

## [Unreleased]

### Added
- Added regression test for `MemoryStore(":memory:")` to ensure in-memory persistence works across operations.
- Added explicit roadmap position summary to clarify current phase, completed core foundations, and next milestone focus.
- Added SQLite-backed memory persistence for chat history, including generated/reused conversation IDs.
- Added Ollama provider support with configurable base URL and model via environment variables.
- Added unit tests for memory store behavior and provider selection routing.

### Fixed
- Fixed SQLite `:memory:` support in `MemoryStore` by reusing a persistent in-memory connection so table initialization and reads/writes share the same database.
- Re-ran full unit test suite after SQLite memory + Ollama integration verification; all tests pass as expected.
- Added unit tests for health and chat endpoint behavior (auth required, auth rejection, and no-API-key fallback) so roadmap/documentation changes are validated by executable checks.

### Documentation
- Clarified that GitHub SSH keys must belong to the pushing user/machine (or CI), not this transient agent container.
- Documented sandbox/proxy environment limits that can block outbound GitHub push despite successful local tests and commits.
- Added SSH-first GitHub push instructions (remote switch, key creation, and verification) to bypass HTTPS proxy tunnel failures.
- Expanded GitHub 403 guidance with a prevention checklist (NO_PROXY retry, allowlist targets, SSH fallback, and auth checks).
- Added README troubleshooting steps for GitHub proxy tunnel errors (`CONNECT tunnel failed, response 403`).
- Added explicit instructions for configuring the GitHub `origin` remote before pushing `dev`.
- Clarified development workflow: `git commit` is local, and `git push origin dev` is required to publish commits on GitHub.
- Added initial changelog file for tracking project evolution.
