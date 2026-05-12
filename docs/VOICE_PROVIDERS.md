# Voice providers

LIBRA treats voice as a swappable capability. Every provider implements
the same interface on both sides of the wire:

- **Backend:** `apps/api/app/services/voice/base.py` (`VoiceProvider` ABC)
- **Frontend:** `apps/web/src/lib/voice/types.ts` (`VoiceClient` interface)

Routes and UI components only depend on those interfaces. To add a new
provider you implement both sides and register it in the two registry
files. Nothing else should change.

---

## 1. OpenAI Realtime (default in v0.1)

**Status:** ready

**Flow:** speech-to-speech, one model, browser ↔ OpenAI over WebRTC.

| Stage         | Where                                          |
| ------------- | ---------------------------------------------- |
| Session mint  | Backend `POST /v1/realtime/sessions`           |
| Token         | Short-lived `client_secret` returned to browser|
| Media         | Browser WebRTC peer connection to OpenAI       |
| Events        | Data channel (`oai-events`)                    |

**Why it's the default**

- Lowest end-to-end latency (no extra server hops for audio).
- Single integration. STT, reasoning, and TTS are all OpenAI.
- The browser holds only an ephemeral key.

**Env**

```env
OPENAI_API_KEY=sk-...
OPENAI_REALTIME_MODEL=gpt-realtime
OPENAI_REALTIME_VOICE=alloy
```

**Tradeoffs**

- You're locked to OpenAI voices.
- Quality is great but not custom-cloned.
- If you want a specific persona voice, prefer provider #2.

---

## 2. ElevenLabs + OpenAI reasoning

**Status:** ready (when keys + voice id are configured)

**Flow:** STT (OpenAI Realtime, transcription-only) → reasoning (OpenAI
Responses, streamed) → streaming TTS (ElevenLabs WebSocket
`stream-input`). All three legs run server-side; the browser is just a
PCM transport plus a small JSON event channel.

| Stage     | Where                                                          |
| --------- | -------------------------------------------------------------- |
| STT       | `wss://api.openai.com/v1/realtime?intent=transcription` (server VAD) |
| Reasoning | OpenAI Responses API, streaming                                |
| TTS       | `wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input` |
| Glue      | `apps/api/app/services/voice/elevenlabs_openai_session.py`     |
| Bridge    | `wss://<api>/api/voice/elevenlabs-openai/stream?token=…` (own WS) |
| WS auth   | Single-use 60 s token minted by `POST /api/voice/session`      |

**Why we want this**

- Custom voice cloning / persona voices via ElevenLabs.
- Reasoning model is decoupled from voice — swap models per task.
- Useful as a quality/latency baseline against OpenAI Realtime.

**Env**

```env
OPENAI_API_KEY=sk-...
OPENAI_REASONING_MODEL=gpt-4.1-mini
OPENAI_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe

ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...           # required
ELEVENLABS_MODEL_ID=eleven_flash_v2_5
```

**Browser ↔ backend wire shape**

Single WebSocket carries both audio and control.

- Up — binary frames: 16-bit LE mono PCM at 16 kHz (mic).
- Up — text frames (JSON): `{ "type": "interrupt" }`.
- Down — binary frames: 16-bit LE mono PCM at 16 kHz (TTS audio).
- Down — text frames (JSON): `ready`, `user_transcript[_delta]`,
  `assistant_text[_delta]`, `response_started`, `response_done`,
  `user_speech_started` / `user_speech_stopped`, `flush_audio`, `error`.

**Voice tunables**

The request body of `POST /api/voice/session` accepts an optional
`voiceSettings` field with `{ stability, similarityBoost, speed }`.
These are passed to the ElevenLabs `voice_settings` field on the first
TTS frame and exposed as sliders in the dashboard Settings panel.

| Field           | Range     | Default |
| --------------- | --------- | ------- |
| stability       | 0.0–1.0   | 0.45    |
| similarityBoost | 0.0–1.0   | 0.75    |
| speed           | 0.7–1.2   | 1.0     |

**WS authentication**

`POST /api/voice/session` returns a `wsUrl` already containing a
single-use opaque token. The backend invalidates the token on first
WebSocket consumption and rejects any handshake with a missing,
unknown, or expired token (close code 1008). Tokens live for 60 s.

This shrinks the attack surface of the otherwise un-gated streaming
endpoint to "the user is actively connecting right now". Token state is
in-memory; replaced by proper auth in a later milestone.

**Barge-in**

When the STT layer reports `input_audio_buffer.speech_started`, the
backend cancels the in-flight LLM+TTS task, closes the ElevenLabs WS,
and emits `user_speech_started` with `flush_audio: true`. The browser
then drops queued playback (by resetting its scheduling clock).

**Latency notes**

- Audio passes through our backend once in each direction. On localhost
  this is negligible; over WAN add ~RTT to your perceived latency vs
  OpenAI Realtime.
- ElevenLabs `eleven_flash_v2_5` is the lowest-latency model (~75 ms
  TTFB). `eleven_turbo_v2_5` trades a little latency for better prosody.

**Tradeoffs vs OpenAI Realtime**

- Higher latency end-to-end (three providers chained, more network
  hops, no single in-model SST↔TTS link).
- Better voice fidelity and persona customization via ElevenLabs.
- More moving parts to monitor and debug.

---

## Adding a third provider

1. Implement `VoiceProvider` in `apps/api/app/services/voice/<name>.py`.
2. Register it in `apps/api/app/services/voice/registry.py`.
3. Extend `VoiceProviderId` in `packages/shared-types/src/voice.ts` and
   in `apps/api/app/schemas/voice.py`.
4. Implement `VoiceClient` in `apps/web/src/lib/voice/<name>.ts`.
5. Register the factory in `apps/web/src/lib/voice/registry.ts`.

The dashboard will pick it up automatically via `/api/voice/providers`.

---

## Security guarantees

- The browser **never** receives `OPENAI_API_KEY` or
  `ELEVENLABS_API_KEY`. Only short-lived, scope-limited credentials.
- Any provider that cannot produce a short-lived credential must proxy
  audio through the backend instead of leaking a long-lived key.
