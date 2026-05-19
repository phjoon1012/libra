import type {
  MemoryFact,
  MemoryFactListResponse,
  SystemStatusResponse,
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
    memoryEnabled?: boolean;
  } = {},
): Promise<VoiceSessionResponse> {
  const resp = await fetch(`${API_BASE}/api/voice/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, ...options }),
  });
  return jsonOrThrow<VoiceSessionResponse>(resp);
}

export async function captureTurn(
  sessionId: string,
  role: "user" | "assistant",
  content: string,
): Promise<void> {
  if (!content.trim()) return;
  const resp = await fetch(
    `${API_BASE}/api/voice/session/${sessionId}/turn`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role, content }),
    },
  );
  if (!resp.ok && resp.status !== 204) {
    // Memory failures must not break the conversation; log and move on.
    console.warn("captureTurn failed", resp.status);
  }
}

export async function endVoiceSession(sessionId: string): Promise<void> {
  await fetch(`${API_BASE}/api/voice/session/${sessionId}/end`, {
    method: "POST",
    keepalive: true,
  }).catch(() => undefined);
}

export async function listMemoryFacts(opts: {
  limit?: number;
  offset?: number;
} = {}): Promise<MemoryFactListResponse> {
  const params = new URLSearchParams();
  if (opts.limit != null) params.set("limit", String(opts.limit));
  if (opts.offset != null) params.set("offset", String(opts.offset));
  const resp = await fetch(
    `${API_BASE}/api/memory/facts${params.toString() ? `?${params}` : ""}`,
    { cache: "no-store" },
  );
  return jsonOrThrow<MemoryFactListResponse>(resp);
}

export async function searchMemoryFacts(
  query: string,
  topK = 10,
): Promise<MemoryFact[]> {
  const resp = await fetch(`${API_BASE}/api/memory/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, topK }),
  });
  return jsonOrThrow<MemoryFact[]>(resp);
}

export async function deleteMemoryFact(factId: string): Promise<void> {
  const resp = await fetch(`${API_BASE}/api/memory/facts/${factId}`, {
    method: "DELETE",
  });
  if (!resp.ok && resp.status !== 204) {
    throw new Error(`Failed to delete fact: ${resp.status}`);
  }
}

export async function createMemoryFact(
  content: string,
  importance = 3,
): Promise<MemoryFact> {
  const resp = await fetch(`${API_BASE}/api/memory/facts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, importance }),
  });
  return jsonOrThrow<MemoryFact>(resp);
}

export async function fetchSystemStatus(): Promise<SystemStatusResponse> {
  const resp = await fetch(`${API_BASE}/api/status`, { cache: "no-store" });
  return jsonOrThrow<SystemStatusResponse>(resp);
}

export interface SpotifyStatus {
  configured: boolean;
  connected: boolean;
  spotifyUserId?: string;
  displayName?: string | null;
  product?: string | null;
  scope?: string;
  connectedAt?: string;
}

export async function fetchSpotifyStatus(): Promise<SpotifyStatus> {
  const resp = await fetch(`${API_BASE}/api/integrations/spotify/status`, {
    cache: "no-store",
  });
  return jsonOrThrow<SpotifyStatus>(resp);
}

export function spotifyConnectUrl(): string {
  return `${API_BASE}/api/integrations/spotify/auth/start`;
}

export async function disconnectSpotify(): Promise<void> {
  const resp = await fetch(`${API_BASE}/api/integrations/spotify/disconnect`, {
    method: "POST",
  });
  if (!resp.ok) {
    throw new Error(`Spotify disconnect failed (${resp.status})`);
  }
}

export interface ToolExecuteResult {
  status: "ok" | "error" | "pending" | "denied";
  tool_name: string;
  request_id: string;
  content?: string;
  data?: unknown;
  error?: boolean;
  reason?: string;
}

export async function executeTool(
  toolName: string,
  args: Record<string, unknown>,
  sessionId?: string | null,
): Promise<ToolExecuteResult> {
  const resp = await fetch(`${API_BASE}/api/tools/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      tool_name: toolName,
      args,
      session_id: sessionId ?? undefined,
    }),
  });
  return jsonOrThrow<ToolExecuteResult>(resp);
}
