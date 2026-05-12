import type {
  ConnectionState,
  TranscriptEntry,
  VoiceProviderId,
  VoiceSettings,
} from "@/types/voice";

/** Resolved live deviceIds (post label-fallback) for this connect. */
export interface ResolvedAudioDevices {
  inputDeviceId: string | null;
  outputDeviceId: string | null;
}

export interface VoiceClientEvents {
  onStateChange: (state: ConnectionState) => void;
  onTranscript: (entry: TranscriptEntry) => void;
  onError: (err: Error) => void;
}

export type LevelListener = (level: number) => void;

export interface VoiceClient {
  readonly id: VoiceProviderId;
  connect(): Promise<void>;
  disconnect(): Promise<void>;
  setMuted(muted: boolean): void;
  interrupt(): void;
  /**
   * Subscribe to a stream of normalized output-audio levels (0..1).
   * Implementations should emit at animation-frame rate while audio is
   * playing and 0 when silent. Returns an unsubscribe function.
   */
  subscribeLevel(listener: LevelListener): () => void;
}

export interface VoiceClientOptions {
  events: VoiceClientEvents;
  voice?: string;
  instructions?: string;
  /** ElevenLabs-only tunables; other providers ignore. */
  voiceSettings?: VoiceSettings;
  /** Live deviceIds; null/undefined = use system default. */
  audioDevices?: ResolvedAudioDevices;
}

export type VoiceClientFactory = (opts: VoiceClientOptions) => VoiceClient;
