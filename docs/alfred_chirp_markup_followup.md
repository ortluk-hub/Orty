# Alfred Chirp Markup Follow-Up

Date: 2026-03-21

## Goal

Bring Orty's /v1/tts/synthesize relay up to parity with Alfred's direct Google TTS path so Chirp 3 HD voices can receive markup input instead of only plain text.

## Why

Alfred now prefers a Chirp 3 HD cloud voice first and falls back to Neural2. The direct Google path can send markup for Chirp 3 HD, but Orty currently only accepts 	ext and always forwards input.text to Google TTS. That means Orty-connected devices get the newer voice name, but not the fuller pause shaping Alfred now prepares for Chirp.

## Safe implementation steps

1. Extend SpeechSynthesizeRequest in service/models/schemas.py with an optional markup: str | None field.
2. Update service/api/routes/v1_tts.py so Google request bodies choose exactly one input source in this order:
   - markup when present
   - otherwise 	ext
3. Keep the existing oice_name, speaking_rate, and udio_encoding behavior unchanged.
4. Add tests in 	ests/test_api.py for:
   - plain-text synthesis still working
   - markup synthesis forwarding input.markup
   - requests that omit both 	ext and markup failing validation
5. After Orty lands this, Alfred can optionally start forwarding Chirp markup through the Orty relay as well instead of only on the direct Google path.

## Non-goals for this slice

- Gemini-TTS auth migration
- custom voice cloning
- promptable Gemini speech style instructions
