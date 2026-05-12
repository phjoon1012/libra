"use client";

import { useEffect } from "react";

import { useAudioDevices } from "@/hooks/useAudioDevices";
import type { AudioDevicePreferences } from "@/lib/audio/devices";

interface Props {
  prefs: AudioDevicePreferences;
  onChange: (next: AudioDevicePreferences) => void;
  /** Disabled while a session is connected/connecting (changes apply on next connect). */
  disabled?: boolean;
  outputSinkSupported: boolean;
}

const DEFAULT_OPTION = "__default__";

export function AudioDevicesPanel({
  prefs,
  onChange,
  disabled,
  outputSinkSupported,
}: Props) {
  const { inputs, outputs, labelsUnlocked, requestLabelAccess, refresh } =
    useAudioDevices();

  useEffect(() => {
    // Re-enumerate once on first mount in case devices changed while idle.
    refresh();
  }, [refresh]);

  const handleInputChange = (value: string) => {
    if (value === DEFAULT_OPTION) {
      onChange({ ...prefs, inputDeviceId: null, inputDeviceLabel: null });
      return;
    }
    const dev = inputs.find((d) => d.deviceId === value);
    onChange({
      ...prefs,
      inputDeviceId: value,
      inputDeviceLabel: dev?.label || null,
    });
  };

  const handleOutputChange = (value: string) => {
    if (value === DEFAULT_OPTION) {
      onChange({ ...prefs, outputDeviceId: null, outputDeviceLabel: null });
      return;
    }
    const dev = outputs.find((d) => d.deviceId === value);
    onChange({
      ...prefs,
      outputDeviceId: value,
      outputDeviceLabel: dev?.label || null,
    });
  };

  const selectedInput = prefs.inputDeviceId ?? DEFAULT_OPTION;
  const selectedOutput = prefs.outputDeviceId ?? DEFAULT_OPTION;

  return (
    <div className="flex flex-col gap-3">
      <span className="panel-title">Audio devices</span>

      <label className="flex flex-col gap-1.5">
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/45">
          Microphone
        </span>
        <select
          disabled={disabled}
          value={selectedInput}
          onChange={(e) => handleInputChange(e.target.value)}
          className="rounded-md border border-white/10 bg-transparent px-2.5 py-1.5 text-sm text-white outline-none transition focus:border-white/40 disabled:opacity-40"
        >
          <option value={DEFAULT_OPTION} className="bg-black text-white">
            System default
          </option>
          {inputs.map((d, i) => (
            <option key={d.deviceId} value={d.deviceId} className="bg-black text-white">
              {d.label || `Microphone ${i + 1}`}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/45">
          Output
        </span>
        <select
          disabled={disabled || !outputSinkSupported}
          value={selectedOutput}
          onChange={(e) => handleOutputChange(e.target.value)}
          className="rounded-md border border-white/10 bg-transparent px-2.5 py-1.5 text-sm text-white outline-none transition focus:border-white/40 disabled:opacity-40"
        >
          <option value={DEFAULT_OPTION} className="bg-black text-white">
            System default
          </option>
          {outputs.map((d, i) => (
            <option key={d.deviceId} value={d.deviceId} className="bg-black text-white">
              {d.label || `Output ${i + 1}`}
            </option>
          ))}
        </select>
        {!outputSinkSupported ? (
          <span className="text-[10px] leading-snug text-white/35">
            This browser doesn&apos;t support output routing. Use the OS audio
            switcher.
          </span>
        ) : null}
      </label>

      {!labelsUnlocked ? (
        <button
          type="button"
          onClick={requestLabelAccess}
          className="rounded-md border border-white/15 bg-transparent px-2.5 py-1.5 text-[11px] uppercase tracking-[0.2em] text-white/80 transition hover:border-white/40"
        >
          Reveal device names
        </button>
      ) : null}

      <p className="text-[10px] leading-snug text-white/35">
        Changes apply on next Connect.
      </p>
    </div>
  );
}
