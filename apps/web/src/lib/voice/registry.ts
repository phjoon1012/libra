import type { VoiceProviderId } from "@/types/voice";
import { createElevenLabsOpenAIClient } from "./elevenlabsOpenai";
import { createOpenAIRealtimeClient } from "./openaiRealtime";
import type { VoiceClientFactory } from "./types";

const REGISTRY: Record<VoiceProviderId, VoiceClientFactory> = {
  "openai-realtime": createOpenAIRealtimeClient,
  "elevenlabs-openai": createElevenLabsOpenAIClient,
};

export function getVoiceClientFactory(id: VoiceProviderId): VoiceClientFactory {
  const factory = REGISTRY[id];
  if (!factory) throw new Error(`Unknown voice provider: ${id}`);
  return factory;
}
