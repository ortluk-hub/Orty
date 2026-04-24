# Alfred Tool Pass Handoff - 2026-04-24

Context:
- Alfred now has a client-side compatibility pass for Orty chat tool calls.
- That Alfred build is already installed on the S21 test phone.
- The goal from here is to make Orty return a stable structured contract so Alfred can stop relying on defensive parsing and legacy fallback.

What Alfred now sends on rich /chat requests:
- message
- system_prompt
- ecent_messages
- client
- ssistant_name
- personality_preset
- 	ools
- 	ool_choice = auto

What Alfred now accepts on /chat responses:
- Plain text eply
- Direct structured tool calls:
  - 	ool_calls: [{  name: alfred.navigate_to, arguments: { ... } }]
- OpenAI-style function envelopes:
  - 	oolCalls: [{ function: { name: alfred.navigate_to, arguments:  -encodedCommand LgAuAC4AagBzAG8AbgAuAC4ALgA=  } }]

Canonical target for Orty:
- Return the simpler direct shape:
  - 	ool_calls: [{  name: alfred.compose_sms_contact, arguments: { ... } }]
- Also return metadata when available:
  - handled_by
  - provider
  - allback_used

Current Alfred-local allowlisted tools include:
- timers, reminders, alarms
- app open
- dial/SMS/contact actions
- navigation and saved-location actions
- media control and media selection
- smart home command
- bug report draft

Recommended Orty-side follow-up:
1. Extend service/models/schemas.py ChatRequest to accept Alfred's rich request fields plus 	ools and 	ool_choice.
2. Extend ChatResponse to expose 	ool_calls, handled_by, provider, and allback_used.
3. Update service/api/routes/chat.py to pass rich request context through and return structured metadata unchanged.
4. Update the AI service path so Alfred-targeted local actions are emitted as structured 	ool_calls, not prose.
5. Keep plain-text replies working for non-tool answers.

Notes:
- Alfred still retries a legacy plain /chat payload if Orty rejects the rich request.
- That fallback should remain temporary; the steady-state goal is one shared rich contract across Alfred, GitHub Orty, and orty-server.
- A fuller contract note also exists in the local Orty checkout at:
  - docs/alfred-chat-tool-call-contract-v2.md
