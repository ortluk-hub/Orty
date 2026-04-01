# Orty Feature Request: Codey Supervised Worker Interface

## Purpose

Define the Orty-side interface needed to evolve Codey from a planning bot into Orty's supervised coding arm.

This document is intentionally written from Orty's perspective so a future pass over Orty can make the supervisor, API surface, and event model ready for real Codey task execution.

## Product Direction

Target shape:

- Orty is the supervisor and orchestration layer.
- Codey is the coding specialist, primarily controlled through API.
- Codey's web UI is direct operator access for Robert, but it must sit on top of the same backend task engine Orty uses.

This means Orty should treat Codey as a supervised worker service, not as a freeform chat feature.

## Current State

Today Orty already has:

- authenticated API access
- bot lifecycle APIs
- a bot runner
- bot event storage
- a `codey` bot type

But the current `codey` bot only emits planning/spec events. It does not yet:

- submit real tasks to a Codey service
- track task lifecycle beyond simple bot events
- attach repos or workspaces
- pause, resume, or cancel real Codey work
- ingest Codey artifacts like plans, diffs, logs, and test results

## Requested Orty-Side Capability

Orty should grow a real Codey integration layer that supports supervised coding work with explicit state, artifacts, and review boundaries.

## Required Interface Shape

### 1. Codey task contract

Orty should be able to create and track Codey tasks with structured payloads, not only prompt text.

Minimum task fields:

- `task_type`
- `source_product`
- `title`
- `description`
- `conversation_id`
- `workspace_ref`
- `repo_ref`
- `attachments`
- `priority`
- `approval_mode`
- `requested_by_client_id`

Initial supported task types:

- `bug_report`
- `code_review`
- `implementation_plan`

### 2. Lifecycle mapping

Orty should have a clear mapping between bot state and Codey task state.

Suggested task states:

- `queued`
- `running`
- `blocked`
- `awaiting_approval`
- `completed`
- `failed`
- `cancelled`

Suggested rule:

- Orty bot lifecycle remains the supervisor-facing view.
- Codey task lifecycle is the worker-facing view.
- Orty must persist both without collapsing them into one ambiguous status.

### 3. Event and artifact ingestion

Orty should accept structured events from Codey and store them as bot/task history.

Minimum event families:

- task started
- repo attached
- triage completed
- plan drafted
- approval requested
- patch applied
- verification started
- verification passed
- verification failed
- task completed
- task failed

Minimum artifact families:

- triage report
- implementation plan
- command log
- diff/patch
- test results
- failure summary
- final summary

### 4. Approval boundary support

Orty should be able to enforce supervised behavior before Codey gains write authority.

Minimum approval actions:

- approve next stage
- reject next stage
- request revision
- cancel task

This is especially important for transitions into:

- file writes
- git operations
- test execution with side effects

### 5. Workspace and repo references

Orty needs a stable way to tell Codey what codebase a task belongs to.

Minimum reference types:

- local workspace path
- GitHub `owner/repo`
- optional branch/ref

Required behavior:

- Orty validates inputs before handing them to Codey
- Orty records which repo/workspace was attached to the task
- Orty can show that attachment in bot/task history

### 6. Auth and service identity

Orty and Codey should communicate through a stable service-to-service contract.

Requirements:

- authenticated Codey task API calls
- explicit service identity for Orty when creating tasks
- no user-facing exposure of Codey service secrets
- auditable ownership of Codey-created tasks

### 7. Failure and degraded-mode behavior

Orty should be able to distinguish:

- Codey unavailable
- Codey accepted the task but is blocked
- Codey failed the task
- Codey needs approval
- Codey completed with warnings

Orty should never flatten all of those into a generic bot error.

## First Useful Scope

The first useful Orty-side milestone is not autonomous patching.

It is:

- submit a `bug_report` task to Codey
- attach repo/workspace context
- receive structured triage and implementation plan artifacts
- surface approval controls for the next stage

That already makes Codey useful as Orty's coding arm without allowing unattended writes.

## Out of Scope for the First Orty Pass

- freeform remote shell access through Orty chat
- fully autonomous merges
- hidden write behavior without approval
- a separate special-case Codey chat path unrelated to tasks

## Recommended Orty Work Order

1. Define Orty-side task payload and event schema for Codey tasks.
2. Extend the `codey` bot type from planning stub to external-worker client.
3. Add durable artifact storage and retrieval for Codey task outputs.
4. Add approval APIs and approval-state persistence.
5. Add repo/workspace attachment validation.
6. Add a simple operator-facing status view in existing Orty surfaces.

## Acceptance Gates

### Gate A: Contract ready

- Orty can create a structured Codey task request.
- Orty can persist task metadata and display task status.
- Unit tests cover request validation and state mapping.

### Gate B: Triage ready

- Orty can submit a real bug report task to Codey.
- Orty receives structured triage and plan artifacts.
- Events and artifacts are queryable through Orty APIs.

### Gate C: Supervised execution ready

- Orty can approve or reject the next stage.
- Orty receives patch and verification artifacts from Codey.
- Pause and cancel work end to end.

## Compatibility Reminder

Any future Orty-side implementation should stay aligned with the current Codey roadmap in:

- `/home/ortluk/ortluk-hub/Codey/Projectplan.md`

The two repos should evolve toward one shared task model, not two parallel integration stories.
