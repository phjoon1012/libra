"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

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

import { AudioDevicesPanel } from "./AudioDevicesPanel";
import { AudioOrb } from "./AudioOrb";
import { ConnectionStateBadge } from "./ConnectionState";
import { ControlBar } from "./ControlBar";
import { ProviderSwitcher } from "./ProviderSwitcher";
import { SettingsPanel } from "./SettingsPanel";
import { TranscriptPanel } from "./TranscriptPanel";

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
  const [audioPrefs, setAudioPrefs] =
    useState<AudioDevicePreferences>(EMPTY_AUDIO_PREFS);
  const [providersError, setProvidersError] = useState<string | null>(null);

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
  });

  useEffect(() => {
    setAudioPrefs(loadAudioPreferences());
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
        <ConnectionStateBadge state={session.state} />
      </header>

      <section className="grid flex-1 gap-8 py-10 lg:grid-cols-[240px_1fr_300px]">
        <aside className="flex flex-col gap-8">
          <ProviderSwitcher
            providers={providers}
            active={provider}
            disabled={connectionLocked}
            onChange={handleProviderChange}
          />
          <SettingsPanel
            provider={provider}
            voice={voice}
            onVoiceChange={setVoice}
            instructions={instructions}
            onInstructionsChange={setInstructions}
            voiceSettings={voiceSettings}
            onVoiceSettingsChange={setVoiceSettings}
            disabled={connectionLocked}
          />
          <AudioDevicesPanel
            prefs={audioPrefs}
            onChange={setAudioPrefs}
            disabled={connectionLocked}
            outputSinkSupported={outputSinkSupported}
          />
          {providersError ? (
            <p className="rounded border border-white/15 px-2.5 py-1.5 text-[10px] leading-snug text-white/55">
              Backend unreachable: {providersError}
            </p>
          ) : null}
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
          <TranscriptPanel entries={session.transcript} onClear={session.clearTranscript} />
        </aside>
      </section>

      <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.06] pt-5 font-mono text-[10px] uppercase tracking-ultra text-white/25">
        <span>Local mic · server-side keys</span>
        <span>{new Date().getFullYear()}</span>
      </footer>
    </main>
  );
}
