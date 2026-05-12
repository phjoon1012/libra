"""ElevenLabs + OpenAI streaming voice session orchestrator.

Pipeline:

    browser mic PCM ──► backend WS ──► OpenAI Realtime (STT-only, server VAD)
                                           │
                                           ▼ user_speech_started → barge-in
                                           ▼ final transcript
                                           │
                                           ▼
                                      OpenAI Responses (LLM, streaming)
                                           │
                                           ▼ text token deltas
                                           │
                                           ▼
                                  ElevenLabs WS  (stream-input TTS)
                                           │
                                           ▼ PCM audio frames
                                           ▼
    browser audio out  ◄── backend WS ◄────┘
    control events JSON ◄──────────────────┘

Long-lived keys live only on the backend. The browser gets raw PCM in both
directions and a small JSON event channel multiplexed over the same socket.

Barge-in: when the STT layer reports ``input_audio_buffer.speech_started``,
the in-flight LLM+TTS task is cancelled, the TTS socket is reset, and we
push a ``flush_audio`` event so the browser drops queued playback.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

import websockets
from fastapi import WebSocket, WebSocketDisconnect
from openai import AsyncOpenAI
from websockets.asyncio.client import ClientConnection

from app.core.config import Settings

logger = logging.getLogger(__name__)

INPUT_SAMPLE_RATE = 16_000  # mic PCM 16-bit LE
OUTPUT_SAMPLE_RATE = 16_000  # ElevenLabs pcm_16000

_OPENAI_REALTIME_WS = "wss://api.openai.com/v1/realtime"
_ELEVEN_TTS_WS = (
    "wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input"
    "?model_id={model_id}&output_format=pcm_16000"
)


class ElevenLabsOpenAISession:
    """One end-to-end session bound to a single browser WebSocket."""

    def __init__(
        self,
        browser_ws: WebSocket,
        settings: Settings,
        instructions: str | None,
        *,
        voice_stability: float = 0.45,
        voice_similarity_boost: float = 0.75,
        voice_speed: float = 1.0,
    ) -> None:
        self.browser = browser_ws
        self.settings = settings
        self.instructions = instructions or (
            "You are LIBRA, a calm, concise personal AI companion. "
            "Speak in short natural responses unless asked for detail."
        )
        self.voice_stability = voice_stability
        self.voice_similarity_boost = voice_similarity_boost
        self.voice_speed = voice_speed

        self.openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.stt: ClientConnection | None = None

        # Conversation memory for this session only (no persistence in v0.1).
        self.history: list[dict[str, str]] = [
            {"role": "system", "content": self.instructions}
        ]

        # In-flight response task; cancelled on barge-in.
        self.response_task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    # ------------------------------------------------------------------ run

    async def run(self) -> None:
        if not self.settings.openai_api_key:
            await self._send_event(
                {"type": "error", "message": "OPENAI_API_KEY not configured"}
            )
            return
        if not self.settings.elevenlabs_api_key:
            await self._send_event(
                {"type": "error", "message": "ELEVENLABS_API_KEY not configured"}
            )
            return
        if not self.settings.elevenlabs_voice_id:
            await self._send_event(
                {"type": "error", "message": "ELEVENLABS_VOICE_ID not configured"}
            )
            return

        try:
            await self._open_stt()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to open OpenAI STT")
            await self._send_event(
                {"type": "error", "message": f"STT connect failed: {exc}"}
            )
            return

        await self._send_event({"type": "ready"})

        try:
            await asyncio.gather(
                self._pump_browser_to_stt(),
                self._pump_stt_events(),
            )
        except WebSocketDisconnect:
            pass
        finally:
            self._stop.set()
            await self._cancel_response()
            with suppress(Exception):
                if self.stt is not None:
                    await self.stt.close()

    # ------------------------------------------------------------------ STT

    async def _open_stt(self) -> None:
        url = f"{_OPENAI_REALTIME_WS}?intent=transcription"
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        self.stt = await websockets.connect(url, additional_headers=headers)

        # Configure transcription-only session: VAD on, no model responses.
        await self.stt.send(
            json.dumps(
                {
                    "type": "transcription_session.update",
                    "session": {
                        "input_audio_format": "pcm16",
                        "input_audio_transcription": {
                            "model": self.settings.openai_transcription_model,
                        },
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.5,
                            "prefix_padding_ms": 250,
                            "silence_duration_ms": 600,
                        },
                    },
                }
            )
        )

    async def _pump_browser_to_stt(self) -> None:
        """Browser binary frames are PCM 16-bit LE mono at 16kHz; forward to STT."""
        while not self._stop.is_set():
            try:
                msg = await self.browser.receive()
            except WebSocketDisconnect:
                return

            # Control messages travel as JSON text frames.
            if "text" in msg and msg["text"] is not None:
                await self._handle_browser_control(msg["text"])
                continue

            data: bytes | None = msg.get("bytes")  # type: ignore[assignment]
            if not data or self.stt is None:
                continue

            b64 = base64.b64encode(data).decode("ascii")
            with suppress(Exception):
                await self.stt.send(
                    json.dumps({"type": "input_audio_buffer.append", "audio": b64})
                )

    async def _handle_browser_control(self, raw: str) -> None:
        try:
            evt = json.loads(raw)
        except json.JSONDecodeError:
            return
        kind = evt.get("type")
        if kind == "interrupt":
            await self._cancel_response()
            await self._send_event({"type": "flush_audio"})

    async def _pump_stt_events(self) -> None:
        if self.stt is None:
            return
        async for raw in self.stt:
            if isinstance(raw, bytes):
                continue
            try:
                evt = json.loads(raw)
            except json.JSONDecodeError:
                continue
            await self._handle_stt_event(evt)

    async def _handle_stt_event(self, evt: dict[str, Any]) -> None:
        etype = evt.get("type", "")
        if etype == "input_audio_buffer.speech_started":
            # User just started talking → barge-in.
            await self._cancel_response()
            await self._send_event({"type": "user_speech_started", "flush_audio": True})
        elif etype == "input_audio_buffer.speech_stopped":
            await self._send_event({"type": "user_speech_stopped"})
        elif etype == "conversation.item.input_audio_transcription.delta":
            delta = evt.get("delta", "")
            if delta:
                await self._send_event(
                    {"type": "user_transcript_delta", "delta": delta}
                )
        elif etype == "conversation.item.input_audio_transcription.completed":
            text = (evt.get("transcript") or "").strip()
            if not text:
                return
            await self._send_event({"type": "user_transcript", "text": text})
            await self._begin_response(text)
        elif etype == "error":
            await self._send_event(
                {"type": "error", "message": str(evt.get("error", "STT error"))}
            )

    # ------------------------------------------------------------- response

    async def _cancel_response(self) -> None:
        task = self.response_task
        if task and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
        self.response_task = None

    async def _begin_response(self, user_text: str) -> None:
        await self._cancel_response()
        self.history.append({"role": "user", "content": user_text})
        self.response_task = asyncio.create_task(self._run_response(user_text))

    async def _run_response(self, _user_text: str) -> None:
        await self._send_event({"type": "response_started"})
        assistant_text_parts: list[str] = []
        drain_task: asyncio.Task[None] | None = None
        try:
            async with self._open_tts() as tts:
                # Start draining ElevenLabs audio immediately so the
                # browser begins playback as soon as the first frame is
                # ready — concurrently with the LLM still producing
                # tokens upstream. This is the main latency win.
                drain_task = asyncio.create_task(self._drain_tts(tts))
                try:
                    async for token in self._stream_llm_tokens():
                        if not token:
                            continue
                        assistant_text_parts.append(token)
                        await self._send_event(
                            {"type": "assistant_text_delta", "delta": token}
                        )
                        with suppress(Exception):
                            await tts.send(
                                json.dumps(
                                    {
                                        "text": token,
                                        "try_trigger_generation": True,
                                    }
                                )
                            )
                    # Signal end-of-text so ElevenLabs flushes + emits isFinal.
                    with suppress(Exception):
                        await tts.send(json.dumps({"text": ""}))
                    # Wait for the audio tail.
                    await drain_task
                except BaseException:
                    if drain_task and not drain_task.done():
                        drain_task.cancel()
                        with suppress(asyncio.CancelledError, Exception):
                            await drain_task
                    raise
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("Response pipeline failed")
            await self._send_event(
                {"type": "error", "message": f"Response failed: {exc}"}
            )
            return
        finally:
            text = "".join(assistant_text_parts).strip()
            if text:
                self.history.append({"role": "assistant", "content": text})
                await self._send_event(
                    {"type": "assistant_text", "text": text}
                )
            await self._send_event({"type": "response_done"})

    # ------------------------------------------------------------------ LLM

    async def _stream_llm_tokens(self) -> AsyncIterator[str]:
        # Use the Responses API streaming for forward-looking compatibility.
        stream = await self.openai_client.responses.create(
            model=self.settings.openai_reasoning_model,
            input=[
                {"role": m["role"], "content": m["content"]}  # type: ignore[arg-type]
                for m in self.history
            ],
            stream=True,
        )
        async for event in stream:
            etype = getattr(event, "type", "")
            if etype == "response.output_text.delta":
                yield getattr(event, "delta", "") or ""
            elif etype == "response.error":
                err = getattr(event, "error", None)
                msg = getattr(err, "message", "LLM error")
                raise RuntimeError(msg)
            # Other event types are ignored for this pipeline.

    # ------------------------------------------------------------------ TTS

    def _open_tts(self):  # returns async context manager
        """Open an ElevenLabs WebSocket for streaming TTS input.

        Returns an async context manager so the connection is closed even
        if the response is cancelled mid-flight (barge-in case).
        """

        from contextlib import asynccontextmanager

        url = _ELEVEN_TTS_WS.format(
            voice_id=self.settings.elevenlabs_voice_id,
            model_id=self.settings.elevenlabs_model_id,
        )

        @asynccontextmanager
        async def _cm():
            ws = await websockets.connect(url)
            try:
                # First message: voice settings + auth via xi_api_key field.
                await ws.send(
                    json.dumps(
                        {
                            "text": " ",
                            "voice_settings": {
                                "stability": self.voice_stability,
                                "similarity_boost": self.voice_similarity_boost,
                                "speed": self.voice_speed,
                            },
                            "xi_api_key": self.settings.elevenlabs_api_key,
                        }
                    )
                )
                yield ws
            finally:
                with suppress(Exception):
                    await ws.close()

        return _cm()

    async def _drain_tts(self, ws: ClientConnection) -> None:
        """Forward PCM audio frames from ElevenLabs to the browser."""
        async for raw in ws:
            if isinstance(raw, bytes):
                # Unexpected with our chosen output_format, but pass through.
                await self.browser.send_bytes(raw)
                continue
            try:
                evt = json.loads(raw)
            except json.JSONDecodeError:
                continue
            audio_b64 = evt.get("audio")
            if audio_b64:
                try:
                    pcm = base64.b64decode(audio_b64)
                except (ValueError, TypeError):
                    continue
                with suppress(Exception):
                    await self.browser.send_bytes(pcm)
            if evt.get("isFinal"):
                return

    # ---------------------------------------------------------------- utils

    async def _send_event(self, payload: dict[str, Any]) -> None:
        with suppress(Exception):
            await self.browser.send_text(json.dumps(payload))
