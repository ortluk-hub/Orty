# Alfred-Orty Client Lifecycle Follow-Up

Last updated: 2026-03-30
Status: Next-pass artifact for Orty

## Purpose

Capture the required Orty behavior for Alfred clients that go silent, uninstall, or explicitly disconnect.

This is a prerelease planning artifact for the next Orty pass.

## Problem

Alfred cannot be trusted to notify Orty during uninstall. A client may disappear without sending any final cleanup request.

If Orty keeps treating those clients as active forever, prerelease and production data will accumulate junk:

- dead client registrations
- stale auth state
- misleading active-client views
- orphaned prerelease memory and metadata

## Working Policy

Use `30 days since last successful contact` as the default stale-client threshold.

Client states:

- `active`: client has authenticated or otherwise successfully contacted Orty within the last 30 days
- `stale`: no successful contact for 30 days
- `revoked`: client explicitly disconnected or was disabled by admin action
- optional later: `purged`: client and related prerelease data fully removed after retention window

## Required Server Fields

At minimum, Orty should track:

- `client_id`
- `status`
- `created_at`
- `last_seen_at`
- `revoked_at`
- `revoke_reason`
- `purge_eligible_at`

`last_seen_at` should update only on successful authenticated contact, not on anonymous or failed requests.

## Expected Alfred Behavior

### Explicit disconnect

If the user chooses to disconnect Alfred from Orty:

- Alfred calls an Orty endpoint to revoke/deregister the client
- Orty marks the client `revoked`
- Alfred clears local client credentials and access token state

### Silent uninstall or disappearance

If Alfred disappears without warning:

- Orty does not assume the client is still alive forever
- Orty marks it `stale` after 30 days with no successful contact
- Orty hides or deprioritizes stale clients in active operational views

## Proposed Orty Behavior

### On successful auth or authenticated API usage

- update `last_seen_at`
- if client was `stale`, return it to `active`

### On 30 days without successful contact

- mark client `stale`
- exclude from normal active-client listings and health views
- keep data intact for now

### On explicit disconnect

- mark client `revoked` immediately
- invalidate active bearer tokens
- optionally invalidate long-lived client credentials too, depending on recovery policy

### On longer inactivity window

After a second retention window, likely `60-90 days`, Orty can:

- mark the client purge-eligible
- remove prerelease junk more aggressively
- later decide whether production clients should be archived instead of deleted

## API Follow-Up

Next Orty pass should consider:

- `POST /v1/clients/{client_id}/disconnect` or equivalent authenticated self-revoke route
- admin/client listing filters by `status`
- background stale-client sweep job
- optional admin purge endpoint for prerelease cleanup

## Operational Notes

- Prerelease Orty data is disposable and should be cleaned before Play Store release
- Re-auth should continue to use stored `client_id + client_token`, not silently create replacement clients during ordinary refresh
- Stale detection is a server responsibility, not an Alfred uninstall callback responsibility

## Go/No-Go Questions For Next Pass

- Should explicit disconnect fully revoke long-lived client credentials, or only bearer tokens?
- Should stale clients be reactivated automatically on next successful auth?
- What retention window should be used before purge for prerelease and for production?
- Which admin views need `active/stale/revoked` separation first?
