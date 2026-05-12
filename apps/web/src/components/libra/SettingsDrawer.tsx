"use client";

import { useEffect } from "react";

import type { AudioDevicePreferences } from "@/lib/audio/devices";
import type {
  VoiceProviderDescriptor,
  VoiceProviderId,
  VoiceSettings,
} from "@/types/voice";

import { AudioDevicesPanel } from "./AudioDevicesPanel";
import { ProviderSwitcher } from "./ProviderSwitcher";
import { SettingsPanel } from "./SettingsPanel";
import { SpotifyPanel } from "./SpotifyPanel";

interface Props {
  open: boolean;
  onClose: () => void;

  providers: VoiceProviderDescriptor[];
  provider: VoiceProviderId;
  onProviderChange: (id: VoiceProviderId) => void | Promise<void>;

  voice: string;
  onVoiceChange: (v: string) => void;
  instructions: string;
  onInstructionsChange: (v: string) => void;
  voiceSettings: VoiceSettings;
  onVoiceSettingsChange: (next: VoiceSettings) => void;
  memoryEnabled: boolean;
  onMemoryEnabledChange: (v: boolean) => void;

  audioPrefs: AudioDevicePreferences;
  onAudioPrefsChange: (next: AudioDevicePreferences) => void;
  outputSinkSupported: boolean;

  /** Bumps when the user returns from an OAuth flow, so panels refresh. */
  integrationsRefreshKey?: number;

  /** Locked while the voice session is live. Changes apply on reconnect. */
  disabled: boolean;
  providersError: string | null;
}

export function SettingsDrawer({
  open,
  onClose,
  providers,
  provider,
  onProviderChange,
  voice,
  onVoiceChange,
  instructions,
  onInstructionsChange,
  voiceSettings,
  onVoiceSettingsChange,
  memoryEnabled,
  onMemoryEnabledChange,
  audioPrefs,
  onAudioPrefsChange,
  outputSinkSupported,
  integrationsRefreshKey,
  disabled,
  providersError,
}: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <>
      <div
        aria-hidden
        onClick={onClose}
        className={[
          "fixed inset-0 z-40 bg-black/60 backdrop-blur-sm transition-opacity",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        ].join(" ")}
      />

      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Settings"
        className={[
          "fixed right-0 top-0 z-50 flex h-full w-[min(420px,92vw)] flex-col border-l border-white/10 bg-black shadow-2xl transition-transform duration-200 ease-out",
          open ? "translate-x-0" : "translate-x-full",
        ].join(" ")}
      >
        <header className="flex items-center justify-between border-b border-white/[0.06] px-6 py-4">
          <h2 className="font-mono text-[12px] uppercase tracking-ultra text-white">
            Settings
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close settings"
            className="rounded p-1 text-white/55 transition hover:text-white"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 14 14"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            >
              <path d="M1 1l12 12M13 1L1 13" />
            </svg>
          </button>
        </header>

        <div className="flex flex-1 flex-col gap-7 overflow-y-auto px-6 py-6">
          {disabled ? (
            <p className="rounded border border-amber-300/20 bg-amber-300/[0.04] px-2.5 py-1.5 text-[10px] leading-snug text-amber-200/70">
              Connected — changes apply on next connect.
            </p>
          ) : null}

          <ProviderSwitcher
            providers={providers}
            active={provider}
            disabled={disabled}
            onChange={onProviderChange}
          />

          <SettingsPanel
            provider={provider}
            voice={voice}
            onVoiceChange={onVoiceChange}
            instructions={instructions}
            onInstructionsChange={onInstructionsChange}
            voiceSettings={voiceSettings}
            onVoiceSettingsChange={onVoiceSettingsChange}
            memoryEnabled={memoryEnabled}
            onMemoryEnabledChange={onMemoryEnabledChange}
            disabled={disabled}
          />

          <AudioDevicesPanel
            prefs={audioPrefs}
            onChange={onAudioPrefsChange}
            disabled={disabled}
            outputSinkSupported={outputSinkSupported}
          />

          <SpotifyPanel refreshKey={integrationsRefreshKey} />

          {providersError ? (
            <p className="rounded border border-white/15 px-2.5 py-1.5 text-[10px] leading-snug text-white/55">
              Backend unreachable: {providersError}
            </p>
          ) : null}
        </div>
      </aside>
    </>
  );
}
