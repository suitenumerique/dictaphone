import { AudioInputManager } from '@/features/recordings/recorder/AudioInputManager.ts'
import {
  RecorderChunk,
  RecorderLifecycleState,
} from '@/features/recordings/recorder/types.ts'

const DEFAULT_TIMESLICE_MS = 10_000
const FALLBACK_MIME_TYPE = 'audio/webm'
const LEVEL_MULTIPLIER = 4

type RecorderManagerCallbacks = {
  onChunk?: (chunk: RecorderChunk) => Promise<void> | void
  onStateChange?: (state: RecorderLifecycleState) => void
  onAudioLevel?: (level: number) => void
  onError?: (error: Error) => void
}

type StartRecordingOptions = {
  preferredMimeTypes: string[]
  timesliceMs?: number
  deviceId?: string
}

const resolveMimeType = (preferredMimeTypes: string[]) => {
  for (const mimeType of preferredMimeTypes) {
    if (MediaRecorder.isTypeSupported(mimeType)) {
      return mimeType
    }
  }

  if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
    return 'audio/webm;codecs=opus'
  }

  return FALLBACK_MIME_TYPE
}

/**
 * RecorderManager handles audio recording operations, including managing the lifecycle of a MediaRecorder,
 * ensuring an audio graph setup, and providing audio input switching capabilities.
 *
 * Mostly LLM geneated.
 */
export class RecorderManager {
  private readonly audioInputManager: AudioInputManager
  private readonly callbacks: RecorderManagerCallbacks
  private audioContext: AudioContext | null = null
  private mediaDestination: MediaStreamAudioDestinationNode | null = null
  private inputGainNode: GainNode | null = null
  private analyserNode: AnalyserNode | null = null
  private sourceNode: MediaStreamAudioSourceNode | null = null
  private currentInputStream: MediaStream | null = null
  private mediaRecorder: MediaRecorder | null = null
  private operationQueue = Promise.resolve()
  private sequenceNumber = 0
  private state: RecorderLifecycleState = 'idle'
  private chunkPersistQueue = Promise.resolve()
  private levelAnimationFrameId: number | null = null
  private timesliceMs = DEFAULT_TIMESLICE_MS
  private disposed = false
  private stopResolve: (() => void) | null = null

  constructor(
    audioInputManager: AudioInputManager,
    callbacks: RecorderManagerCallbacks = {}
  ) {
    this.audioInputManager = audioInputManager
    this.callbacks = callbacks

    document.addEventListener('visibilitychange', this.handleVisibilityChange)
  }

  public getState() {
    return this.state
  }

  public getMimeType() {
    return this.mediaRecorder?.mimeType
  }

  private setState(nextState: RecorderLifecycleState) {
    this.state = nextState
    this.callbacks.onStateChange?.(nextState)
  }

  private enqueue<T>(fn: () => Promise<T>) {
    const run = this.operationQueue.then(fn)
    this.operationQueue = run.then(
      () => undefined,
      () => undefined
    )
    return run
  }

  private async ensureAudioGraph() {
    if (
      this.audioContext &&
      this.mediaDestination &&
      this.inputGainNode &&
      this.analyserNode
    ) {
      return
    }

    // We record from a MediaStreamDestination, not directly from the microphone stream.
    // This lets us swap input streams without recreating MediaRecorder.
    this.audioContext = new AudioContext()
    this.mediaDestination = this.audioContext.createMediaStreamDestination()
    this.inputGainNode = this.audioContext.createGain()
    this.inputGainNode.gain.value = 1
    this.analyserNode = this.audioContext.createAnalyser()
    this.analyserNode.fftSize = 1024
    this.analyserNode.smoothingTimeConstant = 0.85

    this.inputGainNode.connect(this.analyserNode)
    this.inputGainNode.connect(this.mediaDestination)
  }

  private async replaceInputStream(stream: MediaStream) {
    if (!this.audioContext || !this.inputGainNode) {
      throw new Error('Audio graph is not initialized')
    }

    this.sourceNode?.disconnect()
    this.sourceNode = null

    if (this.currentInputStream) {
      this.currentInputStream.getTracks().forEach((track) => {
        track.onended = null
        track.stop()
      })
    }

    this.currentInputStream = stream

    for (const track of stream.getAudioTracks()) {
      track.onended = this.handleInputTrackEnded
    }

    this.sourceNode = this.audioContext.createMediaStreamSource(stream)
    this.sourceNode.connect(this.inputGainNode)

    const activeDeviceId = stream.getAudioTracks()[0]?.getSettings().deviceId
    if (activeDeviceId) {
      await this.audioInputManager.selectDevice(activeDeviceId)
    }
  }

  private startLevelLoop() {
    if (!this.analyserNode) {
      return
    }

    const analyser = this.analyserNode
    const samples = new Uint8Array(analyser.fftSize)

    const tick = () => {
      if (this.state !== 'recording') {
        this.callbacks.onAudioLevel?.(0)
        this.levelAnimationFrameId = window.requestAnimationFrame(tick)
        return
      }

      analyser.getByteTimeDomainData(samples)
      let squareSum = 0
      for (const sample of samples) {
        const centered = (sample - 128) / 128
        squareSum += centered * centered
      }
      const rms = Math.sqrt(squareSum / samples.length)
      this.callbacks.onAudioLevel?.(Math.min(1, rms * LEVEL_MULTIPLIER))
      this.levelAnimationFrameId = window.requestAnimationFrame(tick)
    }

    this.levelAnimationFrameId = window.requestAnimationFrame(tick)
  }

  private stopLevelLoop() {
    if (this.levelAnimationFrameId !== null) {
      window.cancelAnimationFrame(this.levelAnimationFrameId)
      this.levelAnimationFrameId = null
    }
    this.callbacks.onAudioLevel?.(0)
  }

  private handleRecorderError = (event: Event) => {
    const recorderError = (event as ErrorEvent).error
    const error =
      recorderError instanceof Error
        ? recorderError
        : new Error('MediaRecorder error')
    this.setState('error')
    this.callbacks.onError?.(error)
  }

  private handleInputTrackEnded = () => {
    void this.enqueue(async () => {
      if (this.state !== 'recording' && this.state !== 'paused') {
        return
      }
      try {
        const stream = await this.audioInputManager.acquireStream()
        await this.replaceInputStream(stream)
      } catch (error) {
        this.callbacks.onError?.(
          error instanceof Error
            ? error
            : new Error('Active microphone ended and could not be recovered')
        )
      }
    })
  }

  private handleVisibilityChange = () => {
    if (!this.audioContext) {
      return
    }
    if (
      document.visibilityState === 'visible' &&
      this.audioContext.state === 'suspended'
    ) {
      void this.audioContext.resume()
    }
  }

  public async start(options: StartRecordingOptions) {
    await this.enqueue(async () => {
      if (this.state !== 'idle' && this.state !== 'stopped') {
        return
      }

      this.setState('starting')
      this.sequenceNumber = 0
      this.timesliceMs = options.timesliceMs ?? DEFAULT_TIMESLICE_MS
      await this.ensureAudioGraph()

      const inputStream = await this.audioInputManager.acquireStream(
        options.deviceId
      )
      await this.replaceInputStream(inputStream)

      const mimeType = resolveMimeType(options.preferredMimeTypes)
      if (!this.mediaDestination) {
        throw new Error('No MediaStreamDestination available')
      }

      const recorder = mimeType
        ? new MediaRecorder(this.mediaDestination.stream, { mimeType })
        : new MediaRecorder(this.mediaDestination.stream)
      this.mediaRecorder = recorder

      recorder.ondataavailable = (event) => {
        if (!event.data || event.data.size === 0) {
          return
        }
        const chunk: RecorderChunk = {
          sequenceNumber: this.sequenceNumber,
          timestamp: Date.now(),
          blob: event.data,
        }
        this.sequenceNumber += 1
        this.chunkPersistQueue = this.chunkPersistQueue.then(async () => {
          await this.callbacks.onChunk?.(chunk)
        })
      }
      recorder.onerror = this.handleRecorderError
      recorder.onstop = () => {
        void this.chunkPersistQueue.finally(() => {
          this.setState('stopped')
          this.stopResolve?.()
          this.stopResolve = null
        })
      }

      recorder.start(this.timesliceMs)
      this.setState('recording')
      this.startLevelLoop()
    })
  }

  public async pause() {
    await this.enqueue(async () => {
      if (!this.mediaRecorder || this.state !== 'recording') {
        return
      }
      this.mediaRecorder.pause()
      this.setState('paused')
    })
  }

  public async resume() {
    await this.enqueue(async () => {
      if (!this.mediaRecorder || this.state !== 'paused') {
        return
      }
      this.mediaRecorder.resume()
      this.setState('recording')
    })
  }

  public async switchInput(deviceId: string) {
    await this.enqueue(async () => {
      await this.audioInputManager.selectDevice(deviceId)
      const nextStream = await this.audioInputManager.acquireStream(deviceId)
      await this.replaceInputStream(nextStream)
    })
  }

  public async stop() {
    await this.enqueue(async () => {
      if (
        !this.mediaRecorder ||
        (this.state !== 'recording' && this.state !== 'paused')
      ) {
        return
      }
      this.setState('stopping')

      await new Promise<void>((resolve) => {
        this.stopResolve = resolve
        this.mediaRecorder?.stop()
      })
    })
  }

  public async dispose() {
    if (this.disposed) {
      return
    }
    this.disposed = true

    await this.enqueue(async () => {
      this.stopLevelLoop()

      if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
        this.mediaRecorder.stop()
      }
      this.mediaRecorder = null

      this.sourceNode?.disconnect()
      this.sourceNode = null

      this.currentInputStream?.getTracks().forEach((track) => {
        track.onended = null
        track.stop()
      })
      this.currentInputStream = null

      this.inputGainNode?.disconnect()
      this.inputGainNode = null
      this.analyserNode?.disconnect()
      this.analyserNode = null
      this.mediaDestination?.disconnect()
      this.mediaDestination = null

      if (this.audioContext) {
        await this.audioContext.close()
        this.audioContext = null
      }

      this.setState('idle')
    })

    document.removeEventListener(
      'visibilitychange',
      this.handleVisibilityChange
    )
  }
}
