// The capture AudioContext performs high-quality resampling to 16 kHz.
// A separate native-rate AudioContext preserves the original playback quality.
class PcmCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.frame = new ArrayBuffer(3200); // 100 ms × 16 kHz × PCM16
    this.view = new DataView(this.frame);
    this.offset = 0;
    this.meterFrames = 0;
    this.peak = 0;
  }
  process(inputs, outputs) {
    const channels = inputs[0];
    for (const output of outputs) for (const channel of output) channel.fill(0);
    if (!channels?.length) return true;
    const count = channels[0].length;
    for (let i = 0; i < count; i++) {
      let sample = 0;
      for (const channel of channels) sample += channel[i] || 0;
      sample = Math.max(-1, Math.min(1, sample / channels.length));
      this.peak = Math.max(this.peak, Math.abs(sample));
      this.view.setInt16(this.offset, sample < 0 ? sample * 32768 : sample * 32767, true);
      this.offset += 2;
      if (this.offset === this.frame.byteLength) {
        this.port.postMessage({ type: "pcm", data: this.frame }, [this.frame]);
        this.frame = new ArrayBuffer(3200);
        this.view = new DataView(this.frame);
        this.offset = 0;
      }
    }
    this.meterFrames += count;
    if (this.meterFrames >= 4000) {
      this.port.postMessage({ type: "meter", peak: this.peak });
      this.peak = 0;
      this.meterFrames = 0;
    }
    return true;
  }
}
registerProcessor("pcm-capture", PcmCapture);
