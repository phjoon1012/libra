"""ElevenLabs + OpenAI streaming voice session orchestrator.

Pipeline:

    browser mic PCM ──► backend WS ──► OpenAI Realtime (STT, browser VAD → commit)
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
import uuid
from contextlib import suppress
from typing import Any

import httpx
import websockets
from fastapi import WebSocket, WebSocketDisconnect
from openai import AsyncOpenAI
from websockets.asyncio.client import ClientConnection

from app.core.config import Settings
from app.core.db import session_scope
from app.core.redis import get_redis
from app.services.memory.service import MemoryService
from app.services.tools import (
    ExecutionContext,
    ToolDenied,
    ToolExecutor,
    ToolPending,
    ToolResult,
    get_registry,
    register_builtin_tools,
)

logger = logging.getLogger(__name__)

INPUT_SAMPLE_RATE = 24_000  # mic PCM 16-bit LE (GA Realtime transcription expects 24 kHz)
OUTPUT_SAMPLE_RATE = 16_000  # ElevenLabs pcm_16000

_OPENAI_REALTIME_WS = "wss://api.openai.com/v1/realtime"
_OPENAI_CLIENT_SECRETS_URL = "https://api.openai.com/v1/realtime/client_secrets"

# GA Realtime ``type: transcription`` sessions (see OpenAI Realtime transcription guide).
# ``gpt-4o-mini-transcribe`` and other file/batch STT models are not valid here.
_TRANSCRIPTION_MODE_MODELS = frozenset({"gpt-realtime-whisper"})
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
        session_id: uuid.UUID,
        user_id: str,
        memory_enabled: bool = True,
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
        self.session_id = session_id
        self.user_id = user_id
        self.memory_enabled = memory_enabled

        self.openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.stt: ClientConnection | None = None

        # System prompt already includes any recall context block injected
        # at session start by the route handler.
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
            await self._finalize_memory()

    # ------------------------------------------------------------------ STT

    async def _open_stt(self) -> None:
        # GA Realtime: mint transcription client_secret, then WebSocket (no ?model=).
        model = self.settings.openai_transcription_model
        if model not in _TRANSCRIPTION_MODE_MODELS:
            supported = ", ".join(sorted(_TRANSCRIPTION_MODE_MODELS))
            raise RuntimeError(
                f"OPENAI_TRANSCRIPTION_MODEL={model!r} is not supported for GA "
                f"Realtime transcription mode. Use one of: {supported}. "
                "(gpt-4o-mini-transcribe is for the Audio API, not this WebSocket path.)"
            )

        # gpt-realtime-whisper does not support server VAD; the browser runs
        # energy VAD and sends commit via control messages.
        session_config: dict[str, object] = {
            "type": "transcription",
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": INPUT_SAMPLE_RATE},
                    "transcription": {"model": model},
                    "turn_detection": None,
                }
            },
        }
        payload = {"session": session_config}

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                _OPENAI_CLIENT_SECRETS_URL,
                headers={
                    "Authorization": f"Bearer {self.settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if resp.status_code >= 400:
                body = resp.text
                logger.error(
                    "OpenAI STT client_secret failed: status=%s body=%s payload=%s",
                    resp.status_code,
                    body,
                    payload,
                )
                raise RuntimeError(f"OpenAI {resp.status_code}: {body}")
            data = resp.json()

        token = data.get("value", "")
        if not token:
            legacy = data.get("client_secret")
            if isinstance(legacy, dict):
                token = legacy.get("value", "")
        if not token:
            raise RuntimeError("OpenAI client_secrets response missing value")

        # Transcription sessions: model is set in client_secrets only — no ?model= on WS.
        ws_headers = {"Authorization": f"Bearer {token}"}
        self.stt = await websockets.connect(_OPENAI_REALTIME_WS, additional_headers=ws_headers)

    async def _pump_browser_to_stt(self) -> None:
        """Browser binary frames are PCM 16-bit LE mono at 24kHz; forward to STT."""
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
        elif kind == "vad":
            speaking = evt.get("speaking")
            if speaking is True:
                await self._cancel_response()
                await self._send_event(
                    {"type": "user_speech_started", "flush_audio": True}
                )
            elif speaking is False and self.stt is not None:
                await self.stt.send(json.dumps({"type": "input_audio_buffer.commit"}))
                await self._send_event({"type": "user_speech_stopped"})

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
            await self._record_turn("user", text)
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

    async def _run_response(self, user_text: str) -> None:
        await self._send_event({"type": "response_started"})
        # Per-turn semantic recall. Builds a transient history for this LLM
        # call only; we do not mutate self.history so future turns aren't
        # polluted with stale context.
        recall_block = await self._recall(user_text)
        if recall_block:
            await self._send_event(
                {"type": "memory_recalled", "block": recall_block}
            )
        llm_history = self._with_recall(self.history, recall_block)
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
                    await self._stream_with_tools(
                        llm_history, tts, assistant_text_parts
                    )
                    # Signal end-of-text so ElevenLabs flushes + emits isFinal.
                    with suppress(Exception):
                        await tts.send(json.dumps({"text": ""}))
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
                await self._record_turn("assistant", text)
            await self._send_event({"type": "response_done"})

    # ------------------------------------------------------------------ LLM

    def _build_tools_arg(self) -> list[dict[str, Any]] | None:
        """Compose the Responses API ``tools`` argument.

        Includes:
        - every Tool in the local registry (function tools)
        - optionally OpenAI's built-in web_search hosted tool

        Returns ``None`` when tools are globally disabled, so the call
        runs as a vanilla text response (cheaper, no tool framing).
        """
        if not self.settings.tools_enabled:
            return None
        register_builtin_tools()
        tools: list[dict[str, Any]] = [
            t.to_openai_tool() for t in get_registry().list()
        ]
        if self.settings.web_search_enabled:
            tools.append({"type": "web_search_preview"})
        return tools or None

    async def _stream_with_tools(
        self,
        history: list[dict[str, str]],
        tts: ClientConnection,
        assistant_text_parts: list[str],
    ) -> None:
        """Drive one assistant turn, including any tool-call rounds.

        Loop:
          1. Stream a Responses API call (tools enabled).
          2. Text deltas → browser + ElevenLabs in real time.
          3. Function-call items collected during the stream.
          4. If any function calls: execute them, append outputs, loop.
          5. Otherwise: done.
        """
        tools_arg = self._build_tools_arg()
        # First round uses the full message history; subsequent rounds
        # use previous_response_id + function_call_output items.
        input_payload: list[dict[str, Any]] = [
            {"role": m["role"], "content": m["content"]}
            for m in history
        ]
        previous_response_id: str | None = None
        ctx = ExecutionContext(
            user_id=self.user_id, session_id=self.session_id
        )

        for _ in range(self.settings.tools_max_iterations):
            text, tool_calls, response_id = await self._llm_round(
                input_payload=input_payload,
                previous_response_id=previous_response_id,
                tools_arg=tools_arg,
                tts=tts,
            )
            if text:
                assistant_text_parts.append(text)
            if not tool_calls:
                return

            tool_outputs = await self._dispatch_tool_calls(tool_calls, ctx)
            previous_response_id = response_id
            input_payload = tool_outputs

        # Hit max iterations without resolution — make sure user isn't
        # left in the dark.
        await self._send_event(
            {
                "type": "error",
                "message": "Tool loop exceeded max iterations.",
            }
        )

    async def _llm_round(
        self,
        *,
        input_payload: list[dict[str, Any]],
        previous_response_id: str | None,
        tools_arg: list[dict[str, Any]] | None,
        tts: ClientConnection,
    ) -> tuple[str, list[dict[str, Any]], str | None]:
        """Stream one Responses API call.

        Returns ``(text, tool_calls, response_id)``. ``tool_calls`` is
        empty when the round finished with pure text.
        """
        kwargs: dict[str, Any] = {
            "model": self.settings.openai_reasoning_model,
            "input": input_payload,
            "stream": True,
        }
        if tools_arg:
            kwargs["tools"] = tools_arg
        if previous_response_id:
            kwargs["previous_response_id"] = previous_response_id

        stream = await self.openai_client.responses.create(**kwargs)

        text_parts: list[str] = []
        # Function-call accumulators keyed by item_id.
        fc_meta: dict[str, dict[str, Any]] = {}
        fc_args: dict[str, list[str]] = {}
        response_id: str | None = None

        async for event in stream:
            etype = getattr(event, "type", "")
            if etype == "response.created":
                r = getattr(event, "response", None)
                if r is not None:
                    response_id = getattr(r, "id", None) or response_id
            elif etype == "response.output_item.added":
                item = getattr(event, "item", None)
                if item is None:
                    continue
                if getattr(item, "type", "") == "function_call":
                    item_id = getattr(item, "id", "") or ""
                    fc_meta[item_id] = {
                        "name": getattr(item, "name", "") or "",
                        "call_id": getattr(item, "call_id", "")
                        or item_id,
                    }
                    fc_args[item_id] = []
            elif etype == "response.function_call_arguments.delta":
                item_id = getattr(event, "item_id", "") or ""
                delta = getattr(event, "delta", "") or ""
                if item_id in fc_args:
                    fc_args[item_id].append(delta)
            elif etype == "response.output_text.delta":
                delta = getattr(event, "delta", "") or ""
                if not delta:
                    continue
                text_parts.append(delta)
                await self._send_event(
                    {"type": "assistant_text_delta", "delta": delta}
                )
                with suppress(Exception):
                    await tts.send(
                        json.dumps(
                            {
                                "text": delta,
                                "try_trigger_generation": True,
                            }
                        )
                    )
            elif etype == "response.completed":
                r = getattr(event, "response", None)
                if r is not None:
                    response_id = getattr(r, "id", None) or response_id
            elif etype == "response.error":
                err = getattr(event, "error", None)
                msg = (
                    getattr(err, "message", "LLM error")
                    if err
                    else "LLM error"
                )
                raise RuntimeError(msg)
            # Other event types (web_search_call.*, output_item.done, etc.)
            # are ignored.

        tool_calls: list[dict[str, Any]] = []
        for item_id, meta in fc_meta.items():
            raw_args = "".join(fc_args.get(item_id, []))
            try:
                parsed = json.loads(raw_args) if raw_args else {}
            except json.JSONDecodeError:
                parsed = {}
            tool_calls.append(
                {
                    "item_id": item_id,
                    "call_id": meta["call_id"],
                    "name": meta["name"],
                    "args": parsed,
                    "args_raw": raw_args,
                }
            )

        return "".join(text_parts), tool_calls, response_id

    async def _dispatch_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
        ctx: ExecutionContext,
    ) -> list[dict[str, Any]]:
        """Execute every tool call sequentially, emit lifecycle events,
        and return the ``function_call_output`` items to feed back."""
        outputs: list[dict[str, Any]] = []
        async with session_scope() as db:
            executor = ToolExecutor(db)
            for tc in tool_calls:
                name = tc["name"]
                call_id = tc["call_id"]
                args = tc["args"]
                await self._send_event(
                    {
                        "type": "tool_call_started",
                        "tool": name,
                        "callId": call_id,
                        "args": args,
                    }
                )
                outcome = await executor.execute(
                    tool_name=name, args=args, ctx=ctx
                )

                if isinstance(outcome, ToolResult):
                    await self._send_event(
                        {
                            "type": "tool_call_completed",
                            "tool": name,
                            "callId": call_id,
                            "content": outcome.content,
                            "data": outcome.data,
                            "error": outcome.error,
                        }
                    )
                    outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": outcome.to_llm_payload(),
                        }
                    )
                elif isinstance(outcome, ToolDenied):
                    await self._send_event(
                        {
                            "type": "tool_call_denied",
                            "tool": name,
                            "callId": call_id,
                            "reason": outcome.reason,
                        }
                    )
                    outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": outcome.to_llm_payload(),
                        }
                    )
                elif isinstance(outcome, ToolPending):
                    # TODO(v0.3-pending-approval): surface the pending
                    # call to the browser and await an approval response
                    # over the same WebSocket. Until that ships, fail
                    # closed so the model doesn't hang.
                    await self._send_event(
                        {
                            "type": "tool_call_pending",
                            "tool": name,
                            "callId": call_id,
                            "scopeKey": outcome.scope_key,
                            "args": args,
                            "note": "approval flow not implemented yet",
                        }
                    )
                    outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": json.dumps(
                                {
                                    "error": True,
                                    "pending": True,
                                    "reason": (
                                        "User approval required but the "
                                        "approval flow is not yet wired."
                                    ),
                                }
                            ),
                        }
                    )
        return outputs

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

    # --------------------------------------------------------------- memory

    @staticmethod
    def _with_recall(
        history: list[dict[str, str]], recall_block: str | None
    ) -> list[dict[str, str]]:
        if not recall_block:
            return history
        # Insert the recall block immediately after the system prompt so
        # it has near-identical weight without overwriting the base
        # personality. The transient list is built per call; not stored.
        out: list[dict[str, str]] = []
        injected = False
        for msg in history:
            out.append(msg)
            if not injected and msg.get("role") == "system":
                out.append({"role": "system", "content": recall_block})
                injected = True
        return out

    async def _record_turn(self, role: str, content: str) -> None:
        if not self.memory_enabled:
            return
        try:
            async with session_scope() as db:
                svc = MemoryService(db=db, redis=get_redis())
                await svc.record_turn(
                    session_id=self.session_id,
                    role=role,  # type: ignore[arg-type]
                    content=content,
                )
        except Exception:
            logger.exception("record_turn failed")

    async def _recall(self, query: str) -> str | None:
        if not self.memory_enabled:
            return None
        try:
            async with session_scope() as db:
                svc = MemoryService(db=db, redis=get_redis())
                return await svc.recall_context_block(
                    user_id=self.user_id, query=query
                )
        except Exception:
            logger.exception("recall failed")
            return None

    async def _finalize_memory(self) -> None:
        """Mark the session ended and schedule distillation. Idempotent."""
        if not self.memory_enabled:
            return
        try:
            async with session_scope() as db:
                svc = MemoryService(db=db, redis=get_redis())
                await svc.end_session(self.session_id)
            async with session_scope() as db:
                svc = MemoryService(db=db, redis=get_redis())
                await svc.schedule_distill(
                    session_id=self.session_id, user_id=self.user_id
                )
        except Exception:
            logger.exception("finalize_memory failed")

    # ---------------------------------------------------------------- utils

    async def _send_event(self, payload: dict[str, Any]) -> None:
        with suppress(Exception):
            await self.browser.send_text(json.dumps(payload))
