import type {
  VoiceProviderDescriptor,
  VoiceProviderId,
  VoiceSessionResponse,
  VoiceSettings,
} from "@/types/voice";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

async function jsonOrThrow<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body?.detail ?? detail;
    } catch {
      // ignore JSON parse errors
    }
    throw new Error(`API ${resp.status}: ${detail}`);
  }
  return (await resp.json()) as T;
}

export async function fetchProviders(): Promise<VoiceProviderDescriptor[]> {
  const resp = await fetch(`${API_BASE}/api/voice/providers`, { cache: "no-store" });
  const body = await jsonOrThrow<{ providers: VoiceProviderDescriptor[] }>(resp);
  return body.providers;
}

export async function createVoiceSession(
  provider: VoiceProviderId,
  options: {
    voice?: string;
    instructions?: string;
    voiceSettings?: VoiceSettings;
  } = {},
): Promise<VoiceSessionResponse> {
  const resp = await fetch(`${API_BASE}/api/voice/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, ...options }),
  });
  return jsonOrThrow<VoiceSessionResponse>(resp);
}
