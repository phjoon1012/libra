// PCM microphone worklet for the ElevenLabs + OpenAI provider.
//
// Receives Float32 mic audio at the AudioContext's native sample rate
// (usually 48 kHz on macOS) and emits 16-bit LE PCM at 24 kHz in
// ~100 ms chunks via this.port.postMessage(Int16Array buffer).
//
// When vadEnabled (default true), also emits { type: "vad", speaking } so
// the backend can commit OpenAI STT turns (gpt-realtime-whisper has no
// server VAD).

class PcmMicProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const opts = (options && options.processorOptions) || {};
    this.targetRate = opts.targetRate || 24000;
    this.chunkMs = opts.chunkMs || 100;
    this.targetChunkSize = Math.floor((this.targetRate * this.chunkMs) / 1000);

    this.ratio = sampleRate / this.targetRate;
    this.acc = new Float32Array(this.targetChunkSize);
    this.accFill = 0;
    this.srcPos = 0;

    this.vadEnabled = opts.vadEnabled !== false;
    this.vadThreshold = opts.vadThreshold ?? 0.018;
    this.vadSilenceChunks = opts.vadSilenceChunks ?? 6;
    this.speaking = false;
    this.silentChunks = 0;
  }

  emitVad(speaking) {
    this.port.postMessage({ type: "vad", speaking });
  }

  updateVad(chunk) {
    if (!this.vadEnabled) return;
    let sum = 0;
    for (let j = 0; j < chunk.length; j++) {
      sum += chunk[j] * chunk[j];
    }
    const rms = Math.sqrt(sum / chunk.length);

    if (rms >= this.vadThreshold) {
      this.silentChunks = 0;
      if (!this.speaking) {
        this.speaking = true;
        this.emitVad(true);
      }
      return;
    }

    if (!this.speaking) return;
    this.silentChunks += 1;
    if (this.silentChunks >= this.vadSilenceChunks) {
      this.speaking = false;
      this.silentChunks = 0;
      this.emitVad(false);
    }
  }

  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch || ch.length === 0) return true;

    for (let i = 0; i < ch.length; i++) {
      this.srcPos += 1;
      if (this.srcPos >= this.ratio) {
        this.srcPos -= this.ratio;
        let s = ch[i];
        if (s > 1) s = 1;
        else if (s < -1) s = -1;
        this.acc[this.accFill++] = s;
        if (this.accFill >= this.targetChunkSize) {
          this.updateVad(this.acc);
          const out = new Int16Array(this.targetChunkSize);
          for (let j = 0; j < this.targetChunkSize; j++) {
            out[j] = Math.round(this.acc[j] * 32767);
          }
          this.port.postMessage(out.buffer, [out.buffer]);
          this.accFill = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor("pcm-mic-processor", PcmMicProcessor);
