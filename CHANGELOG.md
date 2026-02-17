# Changelog

All notable changes to Orty will be documented in this file.

## [Unreleased]

### Added
- Added explicit roadmap position summary to clarify current phase, completed core foundations, and next milestone focus.
- Added SQLite-backed memory persistence for chat history, including generated/reused conversation IDs.
- Added Ollama provider support with configurable base URL and model via environment variables.
- Added unit tests for memory store behavior and provider selection routing.

### Fixed
- Configured `origin` remote to `https://github.com/ortluk-hub/Orty.git`, verified local sanity checks (`pytest -q`: 9 passed), and verified `git push -u origin dev` works when authenticated with a GitHub PAT.
- Re-ran full unit test suite after SQLite memory + Ollama integration verification; all tests pass as expected.
- Added unit tests for health and chat endpoint behavior (auth required, auth rejection, and no-API-key fallback) so roadmap/documentation changes are validated by executable checks.

### Documentation
- Added SSH-first GitHub push instructions (remote switch, key creation, and verification) to bypass HTTPS proxy tunnel failures.
- Expanded GitHub 403 guidance with a prevention checklist (NO_PROXY retry, allowlist targets, SSH fallback, and auth checks).
- Added README troubleshooting steps for GitHub proxy tunnel errors (`CONNECT tunnel failed, response 403`).
- Added explicit instructions for configuring the GitHub `origin` remote before pushing `dev`.
- Clarified which GitHub credentials are required to push after configuring `origin` (HTTPS PAT vs SSH key auth).
- Clarified development workflow: `git commit` is local, and `git push origin dev` is required to publish commits on GitHub.
- Added initial changelog file for tracking project evolution.
