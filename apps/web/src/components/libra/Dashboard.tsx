"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { LIBRA_SYSTEM_PROMPT } from "@libra/prompts";

import { fetchProviders } from "@/lib/api";
import { useAudioDevices } from "@/hooks/useAudioDevices";
import { useVoiceSession } from "@/hooks/useVoiceSession";
import {
  EMPTY_AUDIO_PREFS,
  loadAudioPreferences,
  resolveDeviceId,
  saveAudioPreferences,
  type AudioDevicePreferences,
} from "@/lib/audio/devices";
import {
  DEFAULT_VOICE_SETTINGS,
  type VoiceProviderDescriptor,
  type VoiceProviderId,
  type VoiceSettings,
} from "@/types/voice";

import { AudioOrb } from "./AudioOrb";
import { ConnectionStateBadge } from "./ConnectionState";
import { ControlBar } from "./ControlBar";
import { RightPane } from "./RightPane";
import { SettingsDrawer } from "./SettingsDrawer";
import { StatusPanel } from "./StatusPanel";

const DEFAULT_PROVIDER =
  (process.env.NEXT_PUBLIC_DEFAULT_VOICE_PROVIDER as VoiceProviderId | undefined) ??
  "openai-realtime";

const STATE_LABEL = {
  disconnected: "Awaiting link",
  connecting: "Negotiating session",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
  error: "Fault detected",
} as const;

export function Dashboard() {
  const [providers, setProviders] = useState<VoiceProviderDescriptor[]>([]);
  const [provider, setProvider] = useState<VoiceProviderId>(DEFAULT_PROVIDER);
  const [voice, setVoice] = useState("alloy");
  const [instructions, setInstructions] = useState(LIBRA_SYSTEM_PROMPT);
  const [voiceSettings, setVoiceSettings] = useState<VoiceSettings>(
    DEFAULT_VOICE_SETTINGS,
  );
  const [memoryEnabled, setMemoryEnabled] = useState(true);
  const [audioPrefs, setAudioPrefs] =
    useState<AudioDevicePreferences>(EMPTY_AUDIO_PREFS);
  const [providersError, setProvidersError] = useState<string | null>(null);
  const [memoryRefreshKey, setMemoryRefreshKey] = useState(0);
  const [integrationsRefreshKey, setIntegrationsRefreshKey] = useState(0);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [oauthNotice, setOauthNotice] = useState<string | null>(null);
  const prevStateRef = useRef<string>("disconnected");

  const { inputs: inputDevices, outputs: outputDevices } = useAudioDevices();

  // Resolve stored preferences against the live device list. If the
  // exact deviceId is gone (privacy reset) we fall back to label match.
  const resolvedAudioDevices = useMemo(
    () => ({
      inputDeviceId: resolveDeviceId(
        inputDevices,
        audioPrefs.inputDeviceId,
        audioPrefs.inputDeviceLabel,
      ),
      outputDeviceId: resolveDeviceId(
        outputDevices,
        audioPrefs.outputDeviceId,
        audioPrefs.outputDeviceLabel,
      ),
    }),
    [inputDevices, outputDevices, audioPrefs],
  );

  // setSinkId support detection (Chromium-only as of writing). Driven
  // off the AudioContext prototype rather than HTMLAudioElement because
  // our playback path lives in Web Audio.
  const outputSinkSupported = useMemo(() => {
    if (typeof window === "undefined") return false;
    const Ctx =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    return Boolean(Ctx && "setSinkId" in Ctx.prototype);
  }, []);

  const session = useVoiceSession({
    provider,
    voice,
    instructions,
    voiceSettings,
    audioDevices: resolvedAudioDevices,
    memoryEnabled,
  });

  useEffect(() => {
    setAudioPrefs(loadAudioPreferences());
  }, []);

  // Handle the post-OAuth bounce. URL like `?spotify=connected` or
  // `?spotify=error&reason=...`. We strip the params, refresh the
  // settings panel, and surface a toast-style notice. Errors persist
  // longer than successes so they're harder to miss.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    const spotify = url.searchParams.get("spotify");
    if (!spotify) return;
    let ttlMs = 5000;
    if (spotify === "connected") {
      setOauthNotice("Spotify connected.");
      setIntegrationsRefreshKey((n) => n + 1);
      setSettingsOpen(true);
    } else if (spotify === "error") {
      const reason = url.searchParams.get("reason") ?? "unknown";
      setOauthNotice(`Spotify connect failed: ${reason}`);
      setSettingsOpen(true);
      ttlMs = 20000;
      try {
        window.localStorage.setItem(
          "libra:spotify:last_error",
          JSON.stringify({ reason, ts: Date.now() }),
        );
      } catch {
        // ignore – non-essential
      }
    } else if (spotify === "connected") {
      try {
        window.localStorage.removeItem("libra:spotify:last_error");
      } catch {
        // ignore
      }
    }
    url.searchParams.delete("spotify");
    url.searchParams.delete("reason");
    window.history.replaceState({}, "", url.toString());
    const t = window.setTimeout(() => setOauthNotice(null), ttlMs);
    return () => window.clearTimeout(t);
  }, []);

  useEffect(() => {
    saveAudioPreferences(audioPrefs);
  }, [audioPrefs]);

  useEffect(() => {
    fetchProviders()
      .then((list) => {
        setProviders(list);
        setProvidersError(null);
      })
      .catch((err: Error) => setProvidersError(err.message));
  }, []);

  // When a session ends, the backend kicks off async distillation. Give
  // it a beat, then refresh the memory panel so new facts appear.
  useEffect(() => {
    const prev = prevStateRef.current;
    prevStateRef.current = session.state;
    const wasActive =
      prev !== "disconnected" && prev !== "error" && prev !== "connecting";
    const nowIdle =
      session.state === "disconnected" || session.state === "error";
    if (wasActive && nowIdle) {
      const t = window.setTimeout(
        () => setMemoryRefreshKey((n) => n + 1),
        3000,
      );
      return () => window.clearTimeout(t);
    }
    return undefined;
  }, [session.state]);

  const handleProviderChange = useCallback(
    async (id: VoiceProviderId) => {
      if (session.state !== "disconnected" && session.state !== "error") {
        await session.disconnect();
      }
      setProvider(id);
    },
    [session],
  );

  const connectionLocked =
    session.state !== "disconnected" && session.state !== "error";

  return (
    <main className="mx-auto flex min-h-screen max-w-[1400px] flex-col px-8 py-8">
      <header className="flex items-center justify-between border-b border-white/[0.06] pb-6">
        <div className="flex items-baseline gap-5">
          <h1 className="font-mono text-[15px] font-medium uppercase tracking-ultra text-white">
            Libra
          </h1>
          <span className="font-mono text-[10px] uppercase tracking-[0.28em] text-white/30">
            v0.1
          </span>
        </div>
        <div className="flex items-center gap-4">
          <ConnectionStateBadge state={session.state} />
          <button
            type="button"
            onClick={() => setSettingsOpen(true)}
            aria-label="Open settings"
            className="rounded border border-white/10 p-1.5 text-white/55 transition hover:border-white/30 hover:text-white"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
          </button>
        </div>
      </header>

      <section className="grid flex-1 gap-10 py-10 lg:grid-cols-[220px_1fr_320px]">
        <aside className="flex flex-col">
          <StatusPanel />
        </aside>

        <div className="flex flex-col items-center justify-between gap-10">
          <div className="flex flex-1 flex-col items-center justify-center gap-8">
            <AudioOrb state={session.state} subscribeLevel={session.subscribeLevel} />
            <p className="font-mono text-[11px] uppercase tracking-ultra text-white/40">
              {STATE_LABEL[session.state]}
            </p>
            {session.error ? (
              <p className="max-w-md text-center text-[11px] leading-relaxed text-white/55">
                {session.error}
              </p>
            ) : null}
          </div>
          <ControlBar
            state={session.state}
            muted={session.muted}
            onConnect={session.connect}
            onDisconnect={session.disconnect}
            onToggleMute={session.toggleMute}
            onInterrupt={session.interrupt}
          />
        </div>

        <aside className="flex flex-col lg:max-h-[calc(100vh-12rem)]">
          <RightPane
            entries={session.transcript}
            onClearTranscript={session.clearTranscript}
            memoryRefreshKey={memoryRefreshKey}
          />
        </aside>
      </section>

      <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.06] pt-5 font-mono text-[10px] uppercase tracking-ultra text-white/25">
        <span>Local mic · server-side keys</span>
        <span>{new Date().getFullYear()}</span>
      </footer>

      <SettingsDrawer
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        providers={providers}
        provider={provider}
        onProviderChange={handleProviderChange}
        voice={voice}
        onVoiceChange={setVoice}
        instructions={instructions}
        onInstructionsChange={setInstructions}
        voiceSettings={voiceSettings}
        onVoiceSettingsChange={setVoiceSettings}
        memoryEnabled={memoryEnabled}
        onMemoryEnabledChange={setMemoryEnabled}
        audioPrefs={audioPrefs}
        onAudioPrefsChange={setAudioPrefs}
        outputSinkSupported={outputSinkSupported}
        integrationsRefreshKey={integrationsRefreshKey}
        disabled={connectionLocked}
        providersError={providersError}
      />

      {oauthNotice ? (
        <div
          role="status"
          className="pointer-events-none fixed left-1/2 top-6 z-[60] -translate-x-1/2 rounded border border-white/15 bg-black/85 px-4 py-2 font-mono text-[11px] uppercase tracking-[0.18em] text-white shadow-lg backdrop-blur"
        >
          {oauthNotice}
        </div>
      ) : null}
    </main>
  );
}
