"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { ServiceHealth, ServiceStatus } from "@/types/voice";

/**
 * Watch the browser's microphone, speaker, and camera state.
 *
 * - Mic / camera: use the Permissions API where available
 *   ("granted" / "denied" / "prompt"), and enumerate media devices to
 *   detect hardware presence. Live updates via ``onchange``.
 * - Speaker: no permission API exists. We report "connected" if any
 *   ``audiooutput`` device is enumerated, otherwise fall back to
 *   ``AudioContext`` support detection (some browsers, notably Safari,
 *   don't expose audio outputs without ``selectAudioOutput()``).
 *
 * Returns ``ServiceHealth`` shapes so the status panel can reuse the
 * same dot / label rendering as the backend service probes.
 */
export interface DeviceHealthMap {
  microphone: ServiceHealth;
  speaker: ServiceHealth;
  camera: ServiceHealth;
}

const UNKNOWN: ServiceHealth = { status: "not_configured", detail: null };

function statusFromPermission(
  perm: PermissionState | "unknown",
  hasDevice: boolean,
): ServiceHealth {
  if (perm === "granted") {
    if (!hasDevice) return { status: "error", detail: "no device" };
    return { status: "connected", detail: null };
  }
  if (perm === "denied") return { status: "error", detail: "denied" };
  if (perm === "prompt") return { status: "not_configured", detail: null };
  // unknown: best-effort by device list
  if (hasDevice) return { status: "not_configured", detail: null };
  return { status: "not_configured", detail: null };
}

export function useDeviceStatus(): DeviceHealthMap {
  const [state, setState] = useState<DeviceHealthMap>({
    microphone: UNKNOWN,
    speaker: UNKNOWN,
    camera: UNKNOWN,
  });
  // Hold permission status refs so we can detach onchange listeners.
  const permRefs = useRef<PermissionStatus[]>([]);

  const recompute = useCallback(async () => {
    if (typeof navigator === "undefined" || !navigator.mediaDevices) {
      setState({ microphone: UNKNOWN, speaker: UNKNOWN, camera: UNKNOWN });
      return;
    }

    // Permission states (may throw on unsupported browsers).
    let micPerm: PermissionState | "unknown" = "unknown";
    let camPerm: PermissionState | "unknown" = "unknown";
    if (navigator.permissions?.query) {
      try {
        const r = await navigator.permissions.query({
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          name: "microphone" as any,
        });
        micPerm = r.state;
        permRefs.current.push(r);
        r.onchange = () => void recompute();
      } catch {
        // Older Safari etc.
      }
      try {
        const r = await navigator.permissions.query({
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          name: "camera" as any,
        });
        camPerm = r.state;
        permRefs.current.push(r);
        r.onchange = () => void recompute();
      } catch {
        // Older Safari etc.
      }
    }

    // Device presence.
    let hasMic = false;
    let hasSpeaker = false;
    let hasCam = false;
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      hasMic = devices.some((d) => d.kind === "audioinput");
      hasSpeaker = devices.some((d) => d.kind === "audiooutput");
      hasCam = devices.some((d) => d.kind === "videoinput");
    } catch {
      // Some browsers throw without permission. Keep defaults.
    }

    // Speaker fallback: if no audiooutput is listed (Safari quirk) but
    // AudioContext is supported, assume output is available.
    const audioCtxSupported =
      typeof window !== "undefined" &&
      ("AudioContext" in window ||
        "webkitAudioContext" in (window as unknown as Record<string, unknown>));

    const speaker: ServiceHealth =
      hasSpeaker || audioCtxSupported
        ? { status: "connected", detail: null }
        : { status: "error", detail: "no output" };

    setState({
      microphone: statusFromPermission(micPerm, hasMic),
      speaker,
      camera: statusFromPermission(camPerm, hasCam),
    });
  }, []);

  useEffect(() => {
    void recompute();
    if (typeof navigator === "undefined" || !navigator.mediaDevices)
      return undefined;

    const onDeviceChange = () => void recompute();
    navigator.mediaDevices.addEventListener("devicechange", onDeviceChange);

    return () => {
      navigator.mediaDevices.removeEventListener(
        "devicechange",
        onDeviceChange,
      );
      for (const p of permRefs.current) p.onchange = null;
      permRefs.current = [];
    };
  }, [recompute]);

  return state;
}
