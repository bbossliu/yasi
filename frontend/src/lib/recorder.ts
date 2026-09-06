/** 浏览器录音 → 16kHz 单声道 16bit WAV（讯飞 ASR 要求 wav）。 */
export class WavRecorder {
  private ctx: AudioContext | null = null
  private stream: MediaStream | null = null
  private processor: ScriptProcessorNode | null = null
  private chunks: Float32Array[] = []

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    this.ctx = new AudioContext()
    const source = this.ctx.createMediaStreamSource(this.stream)
    this.processor = this.ctx.createScriptProcessor(4096, 1, 1)
    this.chunks = []
    this.processor.onaudioprocess = (e) => {
      this.chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)))
    }
    source.connect(this.processor)
    this.processor.connect(this.ctx.destination)
  }

  async stop(): Promise<Blob> {
    this.processor?.disconnect()
    this.stream?.getTracks().forEach((t) => t.stop())
    const sampleRate = this.ctx?.sampleRate ?? 48000
    await this.ctx?.close()
    this.ctx = null
    const samples = mergeChunks(this.chunks)
    const pcm16 = downsampleTo16k(samples, sampleRate)
    return encodeWav(pcm16, 16000)
  }
}

function mergeChunks(chunks: Float32Array[]): Float32Array {
  const total = chunks.reduce((n, c) => n + c.length, 0)
  const out = new Float32Array(total)
  let offset = 0
  for (const c of chunks) {
    out.set(c, offset)
    offset += c.length
  }
  return out
}

function downsampleTo16k(samples: Float32Array, fromRate: number): Int16Array {
  const ratio = fromRate / 16000
  const outLen = Math.floor(samples.length / ratio)
  const out = new Int16Array(outLen)
  for (let i = 0; i < outLen; i++) {
    const s = Math.max(-1, Math.min(1, samples[Math.floor(i * ratio)]))
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return out
}

function encodeWav(pcm: Int16Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + pcm.length * 2)
  const view = new DataView(buffer)
  const writeStr = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i))
  }
  writeStr(0, 'RIFF')
  view.setUint32(4, 36 + pcm.length * 2, true)
  writeStr(8, 'WAVE')
  writeStr(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeStr(36, 'data')
  view.setUint32(40, pcm.length * 2, true)
  new Int16Array(buffer, 44).set(pcm)
  return new Blob([buffer], { type: 'audio/wav' })
}
