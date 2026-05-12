"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * Enumerate audio input + output devices and react to changes.
 *
 * Device labels are only populated after the page has been granted
 * microphone permission at least once. `requestLabelAccess` opens and
 * immediately closes a mic track to unlock labels without disturbing
 * an active session.
 */
export function useAudioDevices() {
  const [inputs, setInputs] = useState<MediaDeviceInfo[]>([]);
  const [outputs, setOutputs] = useState<MediaDeviceInfo[]>([]);
  const [labelsUnlocked, setLabelsUnlocked] = useState(false);

  const refresh = useCallback(async () => {
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.enumerateDevices) {
      return;
    }
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const next_inputs = devices.filter((d) => d.kind === "audioinput");
      const next_outputs = devices.filter((d) => d.kind === "audiooutput");
      setInputs(next_inputs);
      setOutputs(next_outputs);
      const anyLabeled = devices.some((d) => d.label.length > 0);
      if (anyLabeled) setLabelsUnlocked(true);
    } catch {
      // Permission denied or unsupported; leave lists empty.
    }
  }, []);

  useEffect(() => {
    refresh();
    if (typeof navigator === "undefined" || !navigator.mediaDevices) return;
    const handler = () => {
      refresh();
    };
    navigator.mediaDevices.addEventListener("devicechange", handler);
    return () => {
      navigator.mediaDevices.removeEventListener("devicechange", handler);
    };
  }, [refresh]);

  /**
   * Briefly request mic access to populate device labels. The track is
   * stopped immediately. Safe to call while a session is active because
   * a separate getUserMedia call doesn't disturb the existing one.
   */
  const requestLabelAccess = useCallback(async () => {
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
      await refresh();
    } catch {
      // Denied — leave UI unchanged.
    }
  }, [refresh]);

  return { inputs, outputs, labelsUnlocked, requestLabelAccess, refresh };
}
