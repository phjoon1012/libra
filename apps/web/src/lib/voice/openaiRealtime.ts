import { captureTurn, createVoiceSession, endVoiceSession } from "@/lib/api";
import type {
  ConnectionState,
  OpenAIRealtimeSession,
  TranscriptEntry,
} from "@/types/voice";
import type { LevelListener, VoiceClient, VoiceClientOptions } from "./types";

/**
 * OpenAI Realtime client.
 *
 * Flow:
 *   1. Ask our backend for an ephemeral client_secret.
 *   2. Get the user's microphone via getUserMedia.
 *   3. Open an RTCPeerConnection, add the mic track, add a data channel.
 *   4. Create an SDP offer, POST it to OpenAI with the client_secret,
 *      and set the returned SDP as the remote description.
 *   5. Play the remote audio track; relay data-channel events to the UI.
 *   6. Tap the remote stream with a Web Audio AnalyserNode and emit
 *      normalized RMS levels so the UI orb can react in real time.
 *
 * The long-lived OPENAI_API_KEY never reaches the browser.
 */
export function createOpenAIRealtimeClient(opts: VoiceClientOptions): VoiceClient {
  const { events, voice, instructions, audioDevices, memoryEnabled } = opts;

  let pc: RTCPeerConnection | null = null;
  let dc: RTCDataChannel | null = null;
  let micStream: MediaStream | null = null;
  let audioCtx: AudioContext | null = null;
  let analyser: AnalyserNode | null = null;
  let analyserSource: MediaStreamAudioSourceNode | null = null;
  let sinkEl: HTMLAudioElement | null = null;
  let levelRaf = 0;
  const levelListeners = new Set<LevelListener>();

  let muted = false;
  let state: ConnectionState = "disconnected";
  let sessionId: string | null = null;
  let pendingAssistantText = "";

  function setState(next: ConnectionState) {
    if (next === state) return;
    state = next;
    events.onStateChange(next);
  }

  function fail(err: unknown) {
    const e = err instanceof Error ? err : new Error(String(err));
    events.onError(e);
    setState("error");
  }

  function emit(entry: Omit<TranscriptEntry, "id" | "ts"> & { id?: string }) {
    events.onTranscript({
      id: entry.id ?? crypto.randomUUID(),
      ts: Date.now(),
      role: entry.role,
      text: entry.text,
      partial: entry.partial,
    });
  }

  function broadcastLevel(level: number) {
    for (const l of levelListeners) l(level);
  }

  function startLevelLoop() {
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
      // RMS for speech is typically ~0.05 quiet to ~0.35 loud; map to 0..1.
      const level = Math.min(1, rms * 3);
      broadcastLevel(level);
      levelRaf = requestAnimationFrame(tick);
    };
    levelRaf = requestAnimationFrame(tick);
  }

  function stopLevelLoop() {
    if (levelRaf) {
      cancelAnimationFrame(levelRaf);
      levelRaf = 0;
    }
    broadcastLevel(0);
  }

  function attachAnalyser(stream: MediaStream) {
    if (!audioCtx) return;
    try {
      analyserSource = audioCtx.createMediaStreamSource(stream);
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 512;
      // Low smoothing so syllable transients survive into the orb.
      analyser.smoothingTimeConstant = 0.35;
      analyserSource.connect(analyser);
      // Route audio through Web Audio for both playback and analysis.
      // Using an <audio> element in parallel causes Chromium to feed the
      // element and leave the analyser reading silence.
      analyser.connect(audioCtx.destination);
      // Nudge the context back to running if anything suspended it.
      audioCtx.resume().catch(() => undefined);
      startLevelLoop();
    } catch {
      // Web Audio not available; orb will simply stay still. Not fatal.
    }
  }

  function teardownAnalyser() {
    stopLevelLoop();
    analyserSource?.disconnect();
    analyser?.disconnect();
    analyserSource = null;
    analyser = null;
    audioCtx?.close().catch(() => undefined);
    audioCtx = null;
  }

  function handleEvent(evt: Record<string, unknown>) {
    const type = evt.type as string | undefined;
    if (!type) return;

    switch (type) {
      case "input_audio_buffer.speech_started":
        setState("listening");
        break;
      case "response.created":
        setState("thinking");
        break;
      case "response.audio.delta":
      case "response.output_audio.delta":
        setState("speaking");
        break;
      case "response.audio_transcript.delta":
      case "response.output_audio_transcript.delta": {
        const delta = (evt.delta as string) ?? "";
        if (delta) {
          pendingAssistantText += delta;
          emit({ role: "assistant", text: delta, partial: true });
        }
        break;
      }
      case "response.audio_transcript.done":
      case "response.output_audio_transcript.done": {
        const text = (evt.transcript as string) ?? pendingAssistantText;
        if (text) {
          emit({ role: "assistant", text });
          if (sessionId && memoryEnabled !== false)
            captureTurn(sessionId, "assistant", text);
        }
        pendingAssistantText = "";
        break;
      }
      case "conversation.item.input_audio_transcription.completed": {
        const text = (evt.transcript as string) ?? "";
        if (text) {
          emit({ role: "user", text });
          if (sessionId && memoryEnabled !== false)
            captureTurn(sessionId, "user", text);
        }
        break;
      }
      case "response.done":
        setState("listening");
        break;
      case "error": {
        const message =
          (evt.error as { message?: string } | undefined)?.message ?? "Realtime error";
        fail(new Error(message));
        break;
      }
      default:
        break;
    }
  }

  async function connect() {
    if (pc) return;
    setState("connecting");

    const log = (...args: unknown[]) => console.log("[libra:oai-realtime]", ...args);

    try {
      log("1/8 requesting backend session…");
      const session = (await createVoiceSession("openai-realtime", {
        voice,
        instructions,
        memoryEnabled,
      })) as OpenAIRealtimeSession;
      sessionId = session.sessionId;
      log("2/8 got session", {
        model: session.model,
        hasSecret: Boolean(session.clientSecret),
        sessionId,
      });

      if (!session.clientSecret) {
        throw new Error(
          "Backend returned no client_secret. Is OPENAI_API_KEY set on the server?",
        );
      }

      // Create + resume the AudioContext synchronously while the click
      // gesture is still active. Doing this lazily (e.g. on ontrack)
      // leaves the context in "suspended" state under Chrome's autoplay
      // policy and produces silence at audioCtx.destination.
      const Ctx =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext: typeof AudioContext })
          .webkitAudioContext;
      audioCtx = new Ctx();
      await audioCtx.resume().catch(() => undefined);
      log("3/8 audio context", audioCtx.state);

      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error(
          "navigator.mediaDevices.getUserMedia is unavailable. " +
            "Use http://localhost (not an IP) or HTTPS.",
        );
      }

      const audioConstraints: MediaTrackConstraints | true = audioDevices?.inputDeviceId
        ? { deviceId: { exact: audioDevices.inputDeviceId } }
        : true;
      log("4/8 requesting microphone…", {
        deviceId: audioDevices?.inputDeviceId ?? "default",
      });
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
      log("5/8 mic granted");

      // Apply output device routing. Prefer AudioContext.setSinkId
      // (Chromium 110+); otherwise fall back to per-element setSinkId on
      // the muted <audio> pump that the WebRTC track is attached to.
      if (audioDevices?.outputDeviceId) {
        const ctxWithSink = audioCtx as AudioContext & {
          setSinkId?: (id: string) => Promise<void>;
        };
        if (typeof ctxWithSink.setSinkId === "function") {
          try {
            await ctxWithSink.setSinkId(audioDevices.outputDeviceId);
          } catch {
            // Will retry on the sink element after it's created.
          }
        }
      }

      // Hidden, muted audio element. Playback happens via
      // audioCtx.destination; this element exists purely to give the
      // WebRTC remote stream an HTMLMediaElement consumer so the
      // browser definitely pumps audio data into the pipeline.
      sinkEl = document.createElement("audio");
      sinkEl.autoplay = true;
      sinkEl.muted = true;
      sinkEl.setAttribute("playsinline", "");
      sinkEl.style.display = "none";
      document.body.appendChild(sinkEl);

      if (audioDevices?.outputDeviceId) {
        const elWithSink = sinkEl as HTMLAudioElement & {
          setSinkId?: (id: string) => Promise<void>;
        };
        if (typeof elWithSink.setSinkId === "function") {
          elWithSink
            .setSinkId(audioDevices.outputDeviceId)
            .catch(() => undefined);
        }
      }

      pc = new RTCPeerConnection();
      pc.ontrack = (e) => {
        const stream = e.streams[0];
        if (!stream) return;
        if (sinkEl) {
          sinkEl.srcObject = stream;
          sinkEl.play().catch(() => undefined);
        }
        attachAnalyser(stream);
      };

      for (const track of micStream.getAudioTracks()) {
        pc.addTrack(track, micStream);
        track.enabled = !muted;
      }

      dc = pc.createDataChannel("oai-events");
      dc.onopen = () => {
        // Do NOT re-send `instructions` here. The backend has already
        // configured the session with an augmented system prompt that
        // includes recalled memory context; pushing the UI's bare prompt
        // here would overwrite that on OpenAI's side and erase recall.
        setState("listening");
      };
      dc.onmessage = (e) => {
        try {
          handleEvent(JSON.parse(e.data));
        } catch {
          // ignore malformed event
        }
      };

      log("6/8 creating offer…");
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      log("7/8 POSTing SDP to OpenAI…");
      const sdpResp = await fetch(
        `${session.realtimeUrl}?model=${encodeURIComponent(session.model)}`,
        {
          method: "POST",
          body: offer.sdp,
          headers: {
            Authorization: `Bearer ${session.clientSecret}`,
            "Content-Type": "application/sdp",
            "OpenAI-Beta": "realtime=v1",
          },
        },
      );
      if (!sdpResp.ok) {
        const detail = await sdpResp.text().catch(() => sdpResp.statusText);
        throw new Error(`OpenAI Realtime SDP exchange failed: ${detail}`);
      }
      const answer: RTCSessionDescriptionInit = {
        type: "answer",
        sdp: await sdpResp.text(),
      };
      await pc.setRemoteDescription(answer);
      log("8/8 connected, awaiting data channel open");
    } catch (err) {
      console.error("[libra:oai-realtime] connect failed", err);
      fail(err);
      await disconnect().catch(() => undefined);
    }
  }

  async function disconnect() {
    const closedSession = sessionId;
    try {
      teardownAnalyser();
      dc?.close();
      micStream?.getTracks().forEach((t) => t.stop());
      pc?.getSenders().forEach((s) => s.track?.stop());
      pc?.close();
    } finally {
      pc = null;
      dc = null;
      micStream = null;
      if (sinkEl) {
        sinkEl.srcObject = null;
        sinkEl.remove();
        sinkEl = null;
      }
      sessionId = null;
      pendingAssistantText = "";
      setState("disconnected");
    }
    if (closedSession && memoryEnabled !== false) {
      endVoiceSession(closedSession).catch(() => undefined);
    }
  }

  function setMuted(next: boolean) {
    muted = next;
    micStream?.getAudioTracks().forEach((t) => (t.enabled = !muted));
  }

  function interrupt() {
    if (dc?.readyState === "open") {
      dc.send(JSON.stringify({ type: "response.cancel" }));
    }
  }

  function subscribeLevel(listener: LevelListener) {
    levelListeners.add(listener);
    return () => {
      levelListeners.delete(listener);
    };
  }

  return {
    id: "openai-realtime",
    connect,
    disconnect,
    setMuted,
    interrupt,
    subscribeLevel,
  };
}
