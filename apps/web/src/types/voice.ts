export type {
  VoiceProviderId,
  VoiceProviderDescriptor,
  VoiceSessionResponse,
  OpenAIRealtimeSession,
  ElevenLabsOpenAISession,
  VoiceSettings,
  MemoryFact,
  MemoryFactListResponse,
  MemorySearchRequest,
  ServiceStatus,
  ServiceHealth,
  SystemStatusResponse,
} from "@libra/shared-types";
export { DEFAULT_VOICE_SETTINGS } from "@libra/shared-types";

export type ConnectionState =
  | "disconnected"
  | "connecting"
  | "listening"
  | "thinking"
  | "speaking"
  | "error";

export interface MessageEntry {
  id: string;
  kind?: "message";
  role: "user" | "assistant" | "system";
  text: string;
  ts: number;
  partial?: boolean;
}

export type ToolEntryState = "started" | "completed" | "denied" | "pending";

export interface ToolEntry {
  id: string;
  kind: "tool";
  ts: number;
  toolName: string;
  callId: string;
  args: Record<string, unknown>;
  state: ToolEntryState;
  /** Result summary string (when completed). */
  content?: string;
  /** Structured result payload (when completed). */
  data?: unknown;
  /** Set when the tool returned an error result. */
  error?: boolean;
  /** Reason text for denied / pending states. */
  reason?: string;
  /** Optional scope (e.g. domain) used by the permission rule. */
  scopeKey?: string;
  /** Wall-clock ms between started -> terminal state. */
  durationMs?: number;
}

export type TranscriptEntry = MessageEntry | ToolEntry;
