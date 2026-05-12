// PCM microphone worklet for the ElevenLabs + OpenAI provider.
//
// Receives Float32 mic audio at the AudioContext's native sample rate
// (usually 48 kHz on macOS) and emits 16-bit LE PCM at 16 kHz in
// ~100 ms chunks via this.port.postMessage(Int16Array buffer).
//
// Resampling is a simple linear decimation, which is fine for speech.

class PcmMicProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const opts = (options && options.processorOptions) || {};
    this.targetRate = opts.targetRate || 16000;
    this.chunkMs = opts.chunkMs || 100;
    this.targetChunkSize = Math.floor((this.targetRate * this.chunkMs) / 1000);

    this.ratio = sampleRate / this.targetRate;
    this.acc = new Float32Array(this.targetChunkSize);
    this.accFill = 0;
    this.srcPos = 0;
  }

  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch || ch.length === 0) return true;

    for (let i = 0; i < ch.length; i++) {
      // Decimate by stepping through source samples at this.ratio.
      // When this.srcPos crosses an integer boundary we sample.
      this.srcPos += 1;
      if (this.srcPos >= this.ratio) {
        this.srcPos -= this.ratio;
        let s = ch[i];
        if (s > 1) s = 1;
        else if (s < -1) s = -1;
        this.acc[this.accFill++] = s;
        if (this.accFill >= this.targetChunkSize) {
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
