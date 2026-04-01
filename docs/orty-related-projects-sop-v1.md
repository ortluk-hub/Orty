# Orty-Related Projects Standard Operating Procedure

## Purpose

This SOP defines the default working method for any project that is part of the Orty ecosystem or expected to integrate with Orty.

Examples include:

- Alfred
- Codey
- future specialist worker projects
- thin clients
- support services that exchange tasks, memory, events, or artifacts with Orty

The goal is to keep multi-repo work consistent, reviewable, and easy to resume.

## Core Principle

Every Orty-related project should be developed as part of one shared system, even when it lives in a separate repo.

That means each project should have:

- a clear local plan
- a clear Orty-facing integration contract or feature request
- explicit test gates
- a simple progress bookmark

No project should rely on tribal memory or chat history alone.

## Standard Required Artifacts

For every Orty-related project, create and maintain all of the following:

### 1. Project plan in the project repo

Each project should have a project-local plan document that captures:

- current state assessment
- target architecture
- slice-by-slice roadmap
- testing gates
- milestone definition

Recommended file name:

- `Projectplan.md`

### 2. Progress bookmark in the project plan

Each project plan should include a `Progress Bookmark` section near the top with:

- bookmark date
- current milestone
- current slice
- slice status
- last green/yellow/red slice
- active blockers
- next resume action
- gate to clear before advancing
- short progress log

This is the single resume point after each work session.

### 3. Orty-facing integration document in the Orty repo

If a project interacts with Orty through auth, tasks, memory, tools, events, or artifacts, Orty should contain a dedicated document describing what Orty needs in order to support that project correctly.

This document may be:

- an integration contract
- a feature request
- a supervisor-worker interface request

Recommended location:

- `docs/<project>-orty-integration-contract-v1.md`
- or `docs/<project>-supervisor-integration-request-v1.md`

### 4. README pointer in Orty

If an Orty-facing integration document exists, Orty's `README.md` should include a visible pointer to it under an integration-oriented section.

### 5. Explicit compatibility section in the project plan

The project-local plan should clearly mark Orty compatibility requirements.

At minimum that section should cover:

- auth expectations
- task API expectations
- event/status contract
- pause/cancel behavior
- artifact/report formats
- repo/workspace reference expectations

## Standard Slice Workflow

Every Orty-related project should advance in slices with explicit gates.

Each slice should define:

- goal
- build work
- testing gate
- stoplight status

### Stoplight meanings

- `Green`: all planned tests pass and at least one realistic end-to-end demo worked
- `Yellow`: core tests pass but one important operational or usability risk remains
- `Red`: the primary gate is still failing; do not advance

Rule:

- do not stack more than one `Yellow` slice in a row
- do not advance past a `Red` slice

## Required Testing Discipline

Every slice should have an explicit gate that can be checked in a repeatable way.

Acceptable gate types include:

- unit tests
- integration tests
- seeded end-to-end flows
- interface contract tests
- fresh-clone setup validation
- manual operator demos when the feature is inherently user-facing

When possible, document the exact command or scenario used to clear the gate.

## Required Orty Compatibility Review

Before a project claims readiness for integration with Orty, it should have a clearly marked compatibility pass that answers:

- How does Orty authenticate to it?
- What tasks or requests can Orty send?
- What events come back?
- What artifacts come back?
- How are failures represented?
- How are pause, cancel, and approval handled?
- What repo or workspace identity is attached to the task?

If those answers are not yet stable, the project is not integration-ready.

## Required Session Closeout

At the end of any substantial work session on an Orty-related project:

1. update the `Progress Bookmark`
2. update the progress log
3. note any new blockers
4. record the next resume action
5. if Orty-facing behavior changed, update the Orty-side integration doc too

## Minimum Milestone Pattern

For most Orty-related worker projects, the recommended milestone pattern is:

### Milestone 1

Safe, read-only usefulness

The project can:

- accept structured input
- inspect relevant context
- produce useful structured output
- avoid unapproved writes or external side effects

### Milestone 2

Supervised execution

The project can:

- act on approved tasks
- return structured events and artifacts
- stop, pause, cancel, and recover cleanly

### Beta

Operator-ready integration

The project can:

- work through Orty
- support direct operator access if applicable
- preserve task history and approvals
- resume work cleanly after interruption

## Current Examples

Current examples that follow this SOP shape:

- Codey project plan: `/home/ortluk/ortluk-hub/Codey/Projectplan.md`
- Codey Orty-side integration request: `docs/codey-supervisor-integration-request-v1.md`
- Alfred-Orty integration contract: `docs/alfred-orty-integration-contract-v1.md`

## Adoption Rule

Going forward, this SOP should be the default operating procedure for all new Orty-related repos unless a project explicitly documents a reason to differ.
