import { AudioInputManager } from '@/features/recordings/recorder/AudioInputManager.ts'
import {
  RecorderChunk,
  RecorderLifecycleState,
} from '@/features/recordings/recorder/types.ts'

const DEFAULT_TIMESLICE_MS = 10_000
const FALLBACK_MIME_TYPE = 'audio/webm'
const FLUSH_WAIT_TIMEOUT_MS = 200

type RecorderManagerCallbacks = {
  onChunk?: (chunk: RecorderChunk) => Promise<void> | void
  onStateChange?: (state: RecorderLifecycleState) => void
  onError?: (error: Error) => void
}

type StartRecordingOptions = {
  preferredMimeTypes: string[]
  timesliceMs?: number
  deviceId?: string
}

const startAudio = new Audio('/assets/sounds/start_recording.ogg')
const stopAudio = new Audio('/assets/sounds/stop_recording.ogg')

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
  private readonly inputStreams = new Set<MediaStream>()
  private mediaRecorder: MediaRecorder | null = null
  private operationQueue = Promise.resolve()
  private sequenceNumber = 0
  private state: RecorderLifecycleState = 'idle'
  private chunkPersistQueue = Promise.resolve()
  private timesliceMs = DEFAULT_TIMESLICE_MS
  private disposed = false
  private stopResolve: (() => void) | null = null

  private stopStreamTracks(stream: MediaStream | null) {
    if (!stream) {
      return
    }
    this.inputStreams.delete(stream)
    stream.getTracks().forEach((track) => {
      track.onended = null
      track.stop()
    })
  }

  private stopAllInputStreams() {
    for (const stream of this.inputStreams) {
      this.stopStreamTracks(stream)
    }
  }

  private ensureNotDisposed() {
    if (this.disposed) {
      throw new Error('RecorderManager has been disposed')
    }
  }

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

  public isDisposed() {
    return this.disposed
  }

  public getMimeType() {
    return this.mediaRecorder?.mimeType
  }

  public getAnalyserNode() {
    return this.analyserNode
  }

  public requestDataFlush() {
    if (this.disposed) {
      return
    }
    if (!this.mediaRecorder) {
      return
    }
    if (this.mediaRecorder.state === 'inactive') {
      return
    }
    if (this.state !== 'recording' && this.state !== 'paused') {
      return
    }
    try {
      this.mediaRecorder.requestData()
    } catch {
      // Ignore best-effort flush failures.
    }
  }

  public async flushPendingChunks(timeoutMs = FLUSH_WAIT_TIMEOUT_MS) {
    await Promise.race([
      this.chunkPersistQueue,
      new Promise<void>((resolve) => {
        window.setTimeout(resolve, timeoutMs)
      }),
    ])
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
    this.ensureNotDisposed()
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
    this.analyserNode.fftSize = 512
    this.analyserNode.smoothingTimeConstant = 0.2

    this.inputGainNode.connect(this.analyserNode)
    this.inputGainNode.connect(this.mediaDestination)
  }

  private async replaceInputStream(stream: MediaStream) {
    this.ensureNotDisposed()
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
    this.inputStreams.add(stream)

    for (const track of stream.getAudioTracks()) {
      track.onended = this.handleInputTrackEnded
    }

    try {
      this.sourceNode = this.audioContext.createMediaStreamSource(stream)
      this.sourceNode.connect(this.inputGainNode)
    } catch (error) {
      this.stopStreamTracks(stream)
      this.currentInputStream = null
      throw error
    }

    const activeDeviceId = stream.getAudioTracks()[0]?.getSettings().deviceId
    if (activeDeviceId) {
      await this.audioInputManager.selectDevice(activeDeviceId)
    }
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
      if (this.disposed) {
        return
      }
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
    this.ensureNotDisposed()
    await this.enqueue(async () => {
      this.ensureNotDisposed()
      if (this.state !== 'idle' && this.state !== 'stopped') {
        return
      }

      this.setState('starting')
      try {
        this.sequenceNumber = 0
        this.timesliceMs = options.timesliceMs ?? DEFAULT_TIMESLICE_MS
        await this.ensureAudioGraph()
        if (this.audioContext?.state === 'suspended') {
          await this.audioContext.resume()
        }

        const inputStream = await this.audioInputManager.acquireStream(
          options.deviceId
        )
        if (this.disposed) {
          this.stopStreamTracks(inputStream)
          throw new Error('RecorderManager has been disposed')
        }
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
          // Clone the chunk before persistence to avoid browser-specific Blob lifecycle issues.
          const persistedChunkBlob = new Blob([event.data], {
            type: event.data.type || mimeType || FALLBACK_MIME_TYPE,
          })
          const chunk: RecorderChunk = {
            sequenceNumber: this.sequenceNumber,
            timestamp: Date.now(),
            blob: persistedChunkBlob,
          }
          this.sequenceNumber += 1
          this.chunkPersistQueue = this.chunkPersistQueue.then(async () => {
            try {
              await this.callbacks.onChunk?.(chunk)
            } catch (error) {
              console.error('Failed to persist recording chunk', error)
            }
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

        void startAudio.play()
        recorder.start(this.timesliceMs)
        this.setState('recording')
      } catch (e) {
        this.setState('idle')
        throw e
      }
    })
  }

  public async pause() {
    if (this.disposed) {
      return
    }
    await this.enqueue(async () => {
      if (this.disposed) {
        return
      }
      if (!this.mediaRecorder || this.state !== 'recording') {
        return
      }
      this.mediaRecorder.pause()
      void stopAudio.play()
      this.setState('paused')
    })
  }

  public async resume() {
    if (this.disposed) {
      return
    }
    await this.enqueue(async () => {
      if (this.disposed) {
        return
      }
      if (!this.mediaRecorder || this.state !== 'paused') {
        return
      }

      void startAudio.play()
      this.mediaRecorder.resume()
      this.setState('recording')
    })
  }

  public async switchInput(deviceId: string) {
    if (this.disposed) {
      return
    }
    await this.enqueue(async () => {
      if (this.disposed) {
        return
      }
      await this.audioInputManager.selectDevice(deviceId)
      const nextStream = await this.audioInputManager.acquireStream(deviceId)
      if (this.disposed) {
        this.stopStreamTracks(nextStream)
        return
      }
      await this.replaceInputStream(nextStream)
    })
  }

  public async stop() {
    if (this.disposed) {
      return
    }
    await this.enqueue(async () => {
      if (this.disposed) {
        return
      }
      if (
        !this.mediaRecorder ||
        (this.state !== 'recording' && this.state !== 'paused')
      ) {
        return
      }
      if (this.state === 'recording') {
        void stopAudio.play()
      }

      this.setState('stopping')

      await new Promise<void>((resolve) => {
        this.stopResolve = resolve
        try {
          this.mediaRecorder?.stop()
        } catch {
          this.stopResolve = null
          resolve()
        }
      })
    })
  }

  public async dispose() {
    if (this.disposed) {
      return
    }
    this.disposed = true

    await this.enqueue(async () => {
      this.stopResolve?.()
      this.stopResolve = null

      if (this.mediaRecorder) {
        this.mediaRecorder.ondataavailable = null
        this.mediaRecorder.onerror = null
        this.mediaRecorder.onstop = null
        if (this.mediaRecorder.state !== 'inactive') {
          try {
            this.mediaRecorder.stop()
          } catch {
            // Ignore stop failures during disposal.
          }
        }
      }
      this.mediaRecorder = null

      this.sourceNode?.disconnect()
      this.sourceNode = null

      this.stopAllInputStreams()
      this.currentInputStream = null

      this.inputGainNode?.disconnect()
      this.inputGainNode = null
      this.analyserNode?.disconnect()
      this.analyserNode = null
      this.stopStreamTracks(this.mediaDestination?.stream ?? null)
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
