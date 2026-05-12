// Re-export shared wire types so components import from one place.
export type {
  VoiceProviderId,
  VoiceProviderDescriptor,
  VoiceSessionResponse,
  OpenAIRealtimeSession,
  ElevenLabsOpenAISession,
  VoiceSettings,
} from "@libra/shared-types";
export { DEFAULT_VOICE_SETTINGS } from "@libra/shared-types";

export type ConnectionState =
  | "disconnected"
  | "connecting"
  | "listening"
  | "thinking"
  | "speaking"
  | "error";

export interface TranscriptEntry {
  id: string;
  role: "user" | "assistant" | "system";
  text: string;
  ts: number;
  partial?: boolean;
}
