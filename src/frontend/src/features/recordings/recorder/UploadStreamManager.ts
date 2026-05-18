import { IndexedDbChunkStore } from '@/features/recordings/recorder/IndexedDbChunkStore.ts'
import {
  UploadOptions,
  UploadResult,
} from '@/features/recordings/recorder/types.ts'

const DEFAULT_CONTENT_TYPE = 'audio/webm'

/**
 * Manages the creation and execution of upload streams for recordings, allowing both streamed uploads
 * and fallback blob uploads, while providing progress tracking and abort functionality.
 */
export class UploadStreamManager {
  private readonly chunkStore: IndexedDbChunkStore
  private readonly inFlightUploads = new Map<string, Promise<UploadResult>>()
  private readonly uploadControllers = new Map<string, AbortController>()

  constructor(chunkStore: IndexedDbChunkStore) {
    this.chunkStore = chunkStore
  }

  /**
   * Creates a readable stream for uploading chunks of data associated with a specific recording.
   *
   * @param {Object} options - Configuration options for creating the upload stream.
   * @param {string} options.recordingId - The unique identifier of the recording to upload.
   * @param {number} options.totalBytes - The total size of the data to be uploaded, in bytes.
   * @param {AbortSignal} [options.signal] - Optional signal to abort the upload process.
   * @param {function} [options.onProgress] - Optional callback function invoked with progress updates during the upload.
   * @returns {ReadableStream<Uint8Array>} A readable stream of the data being uploaded.
   */
  public createUploadStream(options: {
    recordingId: string
    totalBytes: number
    signal?: AbortSignal
    onProgress?: UploadOptions['onProgress']
  }): ReadableStream<Uint8Array> {
    const { recordingId, totalBytes, signal, onProgress } = options
    let uploadedBytes = 0
    const iterator = this.chunkStore
      .getChunkStream(recordingId)
      [Symbol.asyncIterator]()

    return new ReadableStream<Uint8Array>({
      pull: async (controller) => {
        if (signal?.aborted) {
          await iterator.return?.()
          controller.error(new DOMException('Upload aborted', 'AbortError'))
          return
        }

        const next = await iterator.next()
        if (next.done || !next.value) {
          controller.close()
          return
        }

        const bytes = new Uint8Array(await next.value.arrayBuffer())
        uploadedBytes += bytes.byteLength
        onProgress?.({
          uploadedBytes,
          totalBytes,
          percent:
            totalBytes <= 0
              ? 0
              : Math.min(100, Math.round((uploadedBytes / totalBytes) * 100)),
        })
        controller.enqueue(bytes)
      },
      cancel: async () => {
        await iterator.return?.()
      },
    })
  }

  /**
   * Uploads a recording to the server.
   *
   * @param options - Upload options including recording ID, total bytes, signal, and progress callback.
   * @returns A promise that resolves when the upload is complete.
   */
  public async uploadRecording(options: UploadOptions) {
    const currentUpload = this.inFlightUploads.get(options.recordingId)
    if (currentUpload) {
      throw new Error(
        `Upload already running for recording ${options.recordingId}`
      )
    }

    const uploadPromise = this.doUpload(options)
    this.inFlightUploads.set(options.recordingId, uploadPromise)
    try {
      return await uploadPromise
    } finally {
      this.inFlightUploads.delete(options.recordingId)
      this.uploadControllers.delete(options.recordingId)
    }
  }

  private async doUpload(options: UploadOptions) {
    const controller = new AbortController()
    this.uploadControllers.set(options.recordingId, controller)

    if (options.signal) {
      options.signal.addEventListener('abort', () => controller.abort(), {
        once: true,
      })
    }

    try {
      return await this.performStreamingUpload(options, controller.signal)
    } catch (error) {
      const aborted =
        error instanceof DOMException && error.name === 'AbortError'
      if (aborted || controller.signal.aborted) {
        throw error
      }
      return this.performBlobFallbackUpload(options, controller.signal)
    }
  }

  private async performStreamingUpload(
    options: UploadOptions,
    signal: AbortSignal
  ) {
    const body = this.createUploadStream({
      recordingId: options.recordingId,
      totalBytes: options.totalBytes,
      signal,
      onProgress: options.onProgress,
    })

    const requestInit: RequestInit & { duplex: 'half' } = {
      method: options.method ?? 'POST',
      body,
      // Request streaming requires `duplex: "half"` in Chromium and recent Firefox.
      // Safari currently does not fully support streaming upload bodies from fetch.
      duplex: 'half',
      signal,
      headers: {
        'Content-Type': options.contentType ?? DEFAULT_CONTENT_TYPE,
        ...options.headers,
      },
    }

    const response = await fetch(options.url, requestInit)
    const responseText = await response.text().catch(() => undefined)
    if (!response.ok) {
      throw new Error(
        `Streaming upload failed for ${options.recordingId} with status ${response.status}`
      )
    }

    return {
      ok: response.ok,
      status: response.status,
      responseText,
    } satisfies UploadResult
  }

  private async performBlobFallbackUpload(
    options: UploadOptions,
    signal: AbortSignal
  ) {
    const chunks: Blob[] = []
    for await (const chunk of this.chunkStore.getChunkStream(
      options.recordingId
    )) {
      if (signal.aborted) {
        throw new DOMException('Upload aborted', 'AbortError')
      }
      chunks.push(chunk)
    }

    const blob = new Blob(chunks, {
      type: options.contentType ?? DEFAULT_CONTENT_TYPE,
    })

    const response = await fetch(options.url, {
      method: options.method ?? 'POST',
      body: blob,
      signal,
      headers: {
        'Content-Type': options.contentType ?? DEFAULT_CONTENT_TYPE,
        ...options.headers,
      },
    })
    const responseText = await response.text().catch(() => undefined)
    if (!response.ok) {
      throw new Error(
        `Fallback upload failed for ${options.recordingId} with status ${response.status}`
      )
    }

    options.onProgress?.({
      uploadedBytes: blob.size,
      totalBytes: options.totalBytes,
      percent: 100,
    })

    return {
      ok: response.ok,
      status: response.status,
      responseText,
    } satisfies UploadResult
  }

  public cancelUpload(recordingId: string) {
    this.uploadControllers.get(recordingId)?.abort()
  }

  public isUploading(recordingId: string) {
    return this.inFlightUploads.has(recordingId)
  }
}
