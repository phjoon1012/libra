import { createVoiceSession } from "@/lib/api";
import type {
  ConnectionState,
  ElevenLabsOpenAISession,
  TranscriptEntry,
} from "@/types/voice";
import type { LevelListener, VoiceClient, VoiceClientOptions } from "./types";

/**
 * ElevenLabs + OpenAI client.
 *
 * Browser is just a transport for audio and a tiny control channel:
 *
 *   1. Ask backend for a session config (ws URL + sample rates).
 *   2. Open WebSocket to backend.
 *   3. Capture mic, downsample to 16 kHz PCM16 in an AudioWorklet,
 *      send binary frames over the WS.
 *   4. Receive binary PCM frames from backend, schedule playback
 *      via AudioBufferSourceNode chain into an analyser tap so the
 *      orb reacts to output just like the OpenAI Realtime provider.
 *   5. Receive JSON control events (transcripts, state, barge-in).
 */
export function createElevenLabsOpenAIClient(opts: VoiceClientOptions): VoiceClient {
  const { events, instructions, voiceSettings, audioDevices } = opts;

  // --- transport / audio state ----------------------------------------
  let ws: WebSocket | null = null;
  let audioCtx: AudioContext | null = null;
  let micStream: MediaStream | null = null;
  let micSource: MediaStreamAudioSourceNode | null = null;
  let micWorklet: AudioWorkletNode | null = null;
  let playbackGain: GainNode | null = null;
  let analyser: AnalyserNode | null = null;
  let nextStartTime = 0; // for back-to-back scheduling
  let outSampleRate = 16000;
  let muted = false;
  let state: ConnectionState = "disconnected";
  let levelRaf = 0;

  const levelListeners = new Set<LevelListener>();

  // --- helpers --------------------------------------------------------
  const setState = (next: ConnectionState) => {
    if (next === state) return;
    state = next;
    events.onStateChange(next);
  };

  const fail = (err: unknown) => {
    const e = err instanceof Error ? err : new Error(String(err));
    events.onError(e);
    setState("error");
  };

  const emit = (entry: Omit<TranscriptEntry, "id" | "ts"> & { id?: string }) => {
    events.onTranscript({
      id: entry.id ?? crypto.randomUUID(),
      ts: Date.now(),
      role: entry.role,
      text: entry.text,
      partial: entry.partial,
    });
  };

  const broadcastLevel = (level: number) => {
    for (const l of levelListeners) l(level);
  };

  const startLevelLoop = () => {
    if (!analyser || levelRaf) return;
    const buf = new Uint8Array(analyser.fftSize);
    const tick = () => {
      if (!analyser) return;
      analyser.getByteTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) {
        const v = (buf[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / buf.length);
      broadcastLevel(Math.min(1, rms * 3));
      levelRaf = requestAnimationFrame(tick);
    };
    levelRaf = requestAnimationFrame(tick);
  };

  const stopLevelLoop = () => {
    if (levelRaf) {
      cancelAnimationFrame(levelRaf);
      levelRaf = 0;
    }
    broadcastLevel(0);
  };

  // Decode int16 PCM bytes into a Float32 AudioBuffer and schedule it.
  const playPcmFrame = (pcmBytes: ArrayBuffer) => {
    if (!audioCtx || !playbackGain) return;
    const int16 = new Int16Array(pcmBytes);
    if (int16.length === 0) return;
    const frame = audioCtx.createBuffer(1, int16.length, outSampleRate);
    const data = frame.getChannelData(0);
    for (let i = 0; i < int16.length; i++) data[i] = int16[i] / 32768;
    const src = audioCtx.createBufferSource();
    src.buffer = frame;
    src.connect(playbackGain);
    const startAt = Math.max(audioCtx.currentTime + 0.02, nextStartTime);
    src.start(startAt);
    nextStartTime = startAt + frame.duration;
  };

  const flushPlayback = () => {
    // Resetting the scheduled time effectively drops queued frames
    // because new frames will be scheduled at current time. Sources
    // already started cannot be stopped instantly, but the gap is small.
    if (audioCtx) nextStartTime = audioCtx.currentTime;
  };

  // --- WS event handling ---------------------------------------------
  const handleControlEvent = (raw: string) => {
    try {
      const evt = JSON.parse(raw) as Record<string, unknown>;
      switch (evt.type) {
        case "ready":
          setState("listening");
          break;
        case "user_speech_started":
          setState("listening");
          if (evt.flush_audio) flushPlayback();
          break;
        case "user_speech_stopped":
          setState("thinking");
          break;
        case "user_transcript": {
          const text = (evt.text as string) ?? "";
          if (text) emit({ role: "user", text });
          break;
        }
        case "user_transcript_delta": {
          const delta = (evt.delta as string) ?? "";
          if (delta) emit({ role: "user", text: delta, partial: true });
          break;
        }
        case "response_started":
          setState("speaking");
          break;
        case "assistant_text_delta": {
          const delta = (evt.delta as string) ?? "";
          if (delta) emit({ role: "assistant", text: delta, partial: true });
          break;
        }
        case "assistant_text": {
          const text = (evt.text as string) ?? "";
          if (text) emit({ role: "assistant", text });
          break;
        }
        case "response_done":
          setState("listening");
          break;
        case "flush_audio":
          flushPlayback();
          break;
        case "error":
          fail(new Error((evt.message as string) ?? "Pipeline error"));
          break;
      }
    } catch {
      // ignore malformed control event
    }
  };

  // --- mic capture ----------------------------------------------------
  const startMic = async () => {
    if (!audioCtx) return;
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error(
        "navigator.mediaDevices.getUserMedia is unavailable. " +
          "Use http://localhost (not an IP) or HTTPS.",
      );
    }
    const audioConstraints: MediaTrackConstraints | true = audioDevices?.inputDeviceId
      ? { deviceId: { exact: audioDevices.inputDeviceId } }
      : true;
    micStream = await Promise.race<MediaStream>([
      navigator.mediaDevices.getUserMedia({ audio: audioConstraints }),
      new Promise<MediaStream>((_, reject) =>
        setTimeout(
          () =>
            reject(
              new Error(
                "Microphone permission timed out after 15s. " +
                  "Check the address bar for a mic prompt, or unblock the site in browser settings.",
              ),
            ),
          15_000,
        ),
      ),
    ]);
    await audioCtx.audioWorklet.addModule("/pcm-mic-worklet.js");
    micSource = audioCtx.createMediaStreamSource(micStream);
    micWorklet = new AudioWorkletNode(audioCtx, "pcm-mic-processor", {
      processorOptions: { targetRate: 16000, chunkMs: 100 },
      numberOfInputs: 1,
      numberOfOutputs: 0,
    });
    micWorklet.port.onmessage = (e: MessageEvent<ArrayBuffer>) => {
      if (muted) return;
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(e.data);
    };
    micSource.connect(micWorklet);
  };

  const stopMic = () => {
    micWorklet?.disconnect();
    micSource?.disconnect();
    micStream?.getTracks().forEach((t) => t.stop());
    micWorklet = null;
    micSource = null;
    micStream = null;
  };

  // --- public API -----------------------------------------------------
  const connect = async () => {
    if (ws) return;
    setState("connecting");
    const log = (...args: unknown[]) => console.log("[libra:el-oai]", ...args);
    try {
      log("1/6 requesting backend session…");
      const session = (await createVoiceSession("elevenlabs-openai", {
        instructions,
        voiceSettings,
      })) as ElevenLabsOpenAISession;
      log("2/6 got session", { wsUrl: session.wsUrl });
      outSampleRate = session.outputSampleRate;

      const Ctx =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext: typeof AudioContext })
          .webkitAudioContext;
      audioCtx = new Ctx();
      await audioCtx.resume().catch(() => undefined);

      if (audioDevices?.outputDeviceId) {
        const ctxWithSink = audioCtx as AudioContext & {
          setSinkId?: (id: string) => Promise<void>;
        };
        if (typeof ctxWithSink.setSinkId === "function") {
          try {
            await ctxWithSink.setSinkId(audioDevices.outputDeviceId);
          } catch {
            // Browser may reject if the deviceId no longer exists; fall
            // back to default routing silently.
          }
        }
      }
      log("3/6 audio context", audioCtx.state);

      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 512;
      analyser.smoothingTimeConstant = 0.35;
      playbackGain = audioCtx.createGain();
      playbackGain.connect(analyser);
      analyser.connect(audioCtx.destination);
      nextStartTime = audioCtx.currentTime;
      startLevelLoop();

      // Prefer the explicit WS base, otherwise derive it from the HTTP
      // API base (just flip the scheme). Falling back to the page origin
      // would point at the Next.js dev server, which doesn't host the
      // WebSocket.
      const explicit = process.env.NEXT_PUBLIC_API_WS_BASE_URL?.replace(/\/$/, "");
      const httpBase = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
      const derived = httpBase?.replace(/^http/, "ws");
      const base = explicit ?? derived ?? "ws://localhost:8000";
      // session.wsUrl already carries the single-use token + any
      // backend-side config; we just join it with the WS base origin.
      const url = new URL(base + session.wsUrl);
      log("4/6 opening WS", url.toString());

      ws = new WebSocket(url.toString());
      ws.binaryType = "arraybuffer";
      ws.onmessage = (e) => {
        if (typeof e.data === "string") {
          handleControlEvent(e.data);
        } else {
          playPcmFrame(e.data as ArrayBuffer);
        }
      };
      ws.onerror = () => fail(new Error("WebSocket error"));
      ws.onclose = (e) => {
        log("ws closed", { code: e.code, reason: e.reason });
        if (state !== "error") setState("disconnected");
      };
      await new Promise<void>((resolve, reject) => {
        if (!ws) return reject(new Error("ws missing"));
        if (ws.readyState === WebSocket.OPEN) return resolve();
        const timer = setTimeout(
          () => reject(new Error("WebSocket open timed out after 10s")),
          10_000,
        );
        ws.addEventListener(
          "open",
          () => {
            clearTimeout(timer);
            resolve();
          },
          { once: true },
        );
        ws.addEventListener(
          "error",
          () => {
            clearTimeout(timer);
            reject(new Error("ws connect failed"));
          },
          { once: true },
        );
      });
      log("5/6 WS open, requesting mic…");

      await startMic();
      log("6/6 mic streaming");
    } catch (err) {
      console.error("[libra:el-oai] connect failed", err);
      fail(err);
      await disconnect().catch(() => undefined);
    }
  };

  const disconnect = async () => {
    try {
      stopMic();
      stopLevelLoop();
      try {
        ws?.close();
      } catch {
        // ignore
      }
      analyser?.disconnect();
      playbackGain?.disconnect();
      await audioCtx?.close().catch(() => undefined);
    } finally {
      ws = null;
      analyser = null;
      playbackGain = null;
      audioCtx = null;
      setState("disconnected");
    }
  };

  const setMuted = (next: boolean) => {
    muted = next;
    // Mic track stays open; we just stop sending frames. This keeps STT
    // VAD state consistent on the backend.
  };

  const interrupt = () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "interrupt" }));
    }
    flushPlayback();
  };

  const subscribeLevel = (listener: LevelListener) => {
    levelListeners.add(listener);
    return () => {
      levelListeners.delete(listener);
    };
  };

  return {
    id: "elevenlabs-openai",
    connect,
    disconnect,
    setMuted,
    interrupt,
    subscribeLevel,
  };
}
