"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getVoiceClientFactory } from "@/lib/voice";
import type {
  LevelListener,
  ResolvedAudioDevices,
  VoiceClient,
} from "@/lib/voice/types";
import type {
  ConnectionState,
  TranscriptEntry,
  VoiceProviderId,
  VoiceSettings,
} from "@/types/voice";

interface UseVoiceSessionOptions {
  provider: VoiceProviderId;
  voice?: string;
  instructions?: string;
  voiceSettings?: VoiceSettings;
  audioDevices?: ResolvedAudioDevices;
  memoryEnabled?: boolean;
}

export function useVoiceSession({
  provider,
  voice,
  instructions,
  voiceSettings,
  audioDevices,
  memoryEnabled,
}: UseVoiceSessionOptions) {
  const [state, setState] = useState<ConnectionState>("disconnected");
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [muted, setMuted] = useState(false);

  const clientRef = useRef<VoiceClient | null>(null);

  const events = useMemo(
    () => ({
      onStateChange: (s: ConnectionState) => setState(s),
      onTranscript: (entry: TranscriptEntry) => {
        setTranscript((prev) => {
          // Tool events are merged in place by their stable callId so
          // started -> completed updates the same row.
          if (entry.kind === "tool") {
            const idx = prev.findIndex(
              (e) => e.kind === "tool" && e.id === entry.id,
            );
            if (idx >= 0) {
              const merged = { ...prev[idx], ...entry };
              const next = prev.slice();
              next[idx] = merged;
              return next;
            }
            return [...prev, entry];
          }
          // Message merge logic (partial deltas collapse into one row).
          if (entry.partial) {
            const last = prev[prev.length - 1];
            if (
              last &&
              last.kind !== "tool" &&
              last.role === entry.role &&
              last.partial
            ) {
              const merged = {
                ...last,
                text: last.text + entry.text,
                ts: entry.ts,
              };
              return [...prev.slice(0, -1), merged];
            }
            return [...prev, entry];
          }
          const last = prev[prev.length - 1];
          if (
            last &&
            last.kind !== "tool" &&
            last.role === entry.role &&
            last.partial
          ) {
            return [...prev.slice(0, -1), { ...entry, partial: false }];
          }
          return [...prev, { ...entry, partial: false }];
        });
      },
      onError: (e: Error) => setError(e.message),
    }),
    [],
  );

  useEffect(() => {
    return () => {
      clientRef.current?.disconnect().catch(() => undefined);
      clientRef.current = null;
    };
  }, []);

  const connect = useCallback(async () => {
    if (clientRef.current) return;
    setError(null);
    const factory = getVoiceClientFactory(provider);
    const client = factory({
      events,
      voice,
      instructions,
      voiceSettings,
      audioDevices,
      memoryEnabled,
    });
    clientRef.current = client;
    await client.connect();
  }, [
    provider,
    voice,
    instructions,
    voiceSettings,
    audioDevices,
    memoryEnabled,
    events,
  ]);

  const disconnect = useCallback(async () => {
    const client = clientRef.current;
    clientRef.current = null;
    await client?.disconnect();
  }, []);

  const toggleMute = useCallback(() => {
    setMuted((prev) => {
      const next = !prev;
      clientRef.current?.setMuted(next);
      return next;
    });
  }, []);

  const interrupt = useCallback(() => {
    clientRef.current?.interrupt();
  }, []);

  const clearTranscript = useCallback(() => setTranscript([]), []);

  /**
   * Subscribe to output audio level (0..1). Returns an unsubscribe fn.
   * Stable identity so subscribers do not re-bind on every render.
   */
  const subscribeLevel = useCallback((listener: LevelListener) => {
    const client = clientRef.current;
    if (!client) return () => undefined;
    return client.subscribeLevel(listener);
  }, []);

  return {
    state,
    transcript,
    error,
    muted,
    connect,
    disconnect,
    toggleMute,
    interrupt,
    clearTranscript,
    subscribeLevel,
  };
}
