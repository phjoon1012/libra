/**
 * Audio device preference storage + resolution.
 *
 * We persist both the deviceId and the human label. On reload, deviceIds
 * can be re-issued by the browser (especially after a privacy reset), so
 * we resolve label-first against the live device list and fall back to
 * deviceId. If neither matches we return null and the browser uses its
 * system default.
 */

const STORAGE_KEY = "libra:audio-devices:v1";

export interface AudioDevicePreferences {
  inputDeviceId: string | null;
  inputDeviceLabel: string | null;
  outputDeviceId: string | null;
  outputDeviceLabel: string | null;
}

export const EMPTY_AUDIO_PREFS: AudioDevicePreferences = {
  inputDeviceId: null,
  inputDeviceLabel: null,
  outputDeviceId: null,
  outputDeviceLabel: null,
};

export function loadAudioPreferences(): AudioDevicePreferences {
  if (typeof window === "undefined") return EMPTY_AUDIO_PREFS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return EMPTY_AUDIO_PREFS;
    const parsed = JSON.parse(raw) as Partial<AudioDevicePreferences>;
    return { ...EMPTY_AUDIO_PREFS, ...parsed };
  } catch {
    return EMPTY_AUDIO_PREFS;
  }
}

export function saveAudioPreferences(prefs: AudioDevicePreferences): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // Quota or privacy mode — silently ignore.
  }
}

/**
 * Resolve a stored preference against the currently visible devices.
 * Returns the live deviceId to pass to getUserMedia / setSinkId,
 * or null to use the system default.
 */
export function resolveDeviceId(
  devices: MediaDeviceInfo[],
  storedId: string | null,
  storedLabel: string | null,
): string | null {
  if (!devices.length) return null;
  if (storedLabel) {
    const byLabel = devices.find((d) => d.label === storedLabel);
    if (byLabel) return byLabel.deviceId;
  }
  if (storedId) {
    const byId = devices.find((d) => d.deviceId === storedId);
    if (byId) return byId.deviceId;
  }
  return null;
}
