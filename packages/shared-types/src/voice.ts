// Types shared between the Next.js frontend and the FastAPI backend.
// Keep this file minimal and stable: it defines the wire shape of the
// voice provider session endpoints.

export type VoiceProviderId = "openai-realtime" | "elevenlabs-openai";

export interface VoiceProviderDescriptor {
  id: VoiceProviderId;
  label: string;
  description: string;
  status: "ready" | "stub";
}

/** ElevenLabs voice-settings tunables. Only used by elevenlabs-openai. */
export interface VoiceSettings {
  stability: number;
  similarityBoost: number;
  speed: number;
}

export const DEFAULT_VOICE_SETTINGS: VoiceSettings = {
  stability: 0.45,
  similarityBoost: 0.75,
  speed: 1.0,
};

export interface OpenAIRealtimeSession {
  provider: "openai-realtime";
  model: string;
  voice: string;
  /** Short-lived client secret used by the browser to authenticate WebRTC. */
  clientSecret: string;
  /** Unix epoch seconds when clientSecret expires. */
  expiresAt: number;
  /** Realtime WebRTC endpoint to POST the SDP offer to. */
  realtimeUrl: string;
  /** Memory session id; used for turn capture + end-of-session distillation. */
  sessionId: string;
}

export interface ElevenLabsOpenAISession {
  provider: "elevenlabs-openai";
  /** WebSocket URL the browser opens for the full audio pipeline. */
  wsUrl: string;
  /** PCM sample rate the browser must send mic audio at (mono, 16-bit LE). */
  inputSampleRate: number;
  /** PCM sample rate the backend will send back audio at (mono, 16-bit LE). */
  outputSampleRate: number;
  /** Reasoning model id, for display. */
  reasoningModel: string;
  /** ElevenLabs voice id used for this session. */
  voiceId: string;
  /** Memory session id; used for end-of-session distillation. */
  sessionId: string;
}

export type VoiceSessionResponse =
  | OpenAIRealtimeSession
  | ElevenLabsOpenAISession;

/** Memory: a single distilled fact stored long-term. */
export interface MemoryFact {
  id: string;
  userId: string;
  content: string;
  importance: number;
  sourceSessionId: string | null;
  createdAt: string;
  lastRecalledAt: string | null;
  /** Cosine distance (lower = more similar). Only set by /memory/search. */
  score: number | null;
}

export interface MemoryFactListResponse {
  facts: MemoryFact[];
  total: number;
}

export interface MemorySearchRequest {
  query: string;
  topK?: number;
  userId?: string;
}

/** One service's reported health. */
export type ServiceStatus = "connected" | "not_configured" | "error";

export interface ServiceHealth {
  status: ServiceStatus;
  /** Only set when status === "error". Short human-readable reason. */
  detail: string | null;
}

export interface SystemStatusResponse {
  services: {
    openai: ServiceHealth;
    elevenlabs: ServiceHealth;
    database: ServiceHealth;
    redis: ServiceHealth;
  };
}
