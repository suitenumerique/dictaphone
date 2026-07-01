import { StoredChunk } from '@/features/recordings/recorder/types.ts'
import { DBSchema, IDBPDatabase, openDB } from 'idb'

const DATABASE_NAME = 'audio-recorder'
const DATABASE_VERSION = 2
const CHUNKS_STORE = 'chunks'
const LEGACY_RECORDINGS_STORE = 'recordings'
const BY_RECORDING_SEQUENCE_INDEX = 'byRecordingSequence'
const BY_RECORDING_TIMESTAMP_INDEX = 'byRecordingTimestamp'

type RecordingSequenceKey = [string, number]

export interface RecorderDatabaseSchema extends DBSchema {
  [CHUNKS_STORE]: {
    key: number
    value: StoredChunk
    indexes: {
      [BY_RECORDING_SEQUENCE_INDEX]: RecordingSequenceKey
      [BY_RECORDING_TIMESTAMP_INDEX]: RecordingSequenceKey
    }
  }
}

type UpgradeDatabaseWithLegacySupport = IDBPDatabase<RecorderDatabaseSchema> & {
  deleteObjectStore(name: string): void
  objectStoreNames: DOMStringList
}

export const isQuotaExceededError = (error: unknown): boolean => {
  if (!(error instanceof DOMException || error instanceof Error)) {
    return false
  }

  return (
    error.name === 'QuotaExceededError' ||
    error.name === 'NS_ERROR_DOM_QUOTA_REACHED'
  )
}

/**
 * IndexedDB-based chunk store for audio recordings.
 * Helps to keep memory usage low and data safe in regards to browser crashes, etc.
 */
export class IndexedDbChunkStore {
  private dbPromise: Promise<IDBPDatabase<RecorderDatabaseSchema>> | null = null
  private activeRecordingId: string | null = null

  public setActiveRecording(recordingId: string) {
    this.activeRecordingId = recordingId
  }

  /**
   * Tries to enable persistent storage, but does not treat rejection as fatal.
   * Browsers may return false without showing any prompt.
   */
  public async ensurePersistentStorage(): Promise<'granted' | 'best-effort'> {
    if (!navigator.storage?.persisted) {
      return 'best-effort'
    }

    try {
      const persisted = await navigator.storage.persisted()
      if (persisted) {
        return 'granted'
      }
    } catch (error) {
      console.error('Error checking persistent storage status:', error)
      return 'best-effort'
    }

    if (!navigator.storage?.persist) {
      return 'best-effort'
    }

    try {
      const granted = await navigator.storage.persist()
      return granted ? 'granted' : 'best-effort'
    } catch (error) {
      console.error('Error requesting persistent storage permission:', error)
      return 'best-effort'
    }
  }

  public async openDatabase() {
    if (!this.dbPromise) {
      this.dbPromise = openDB<RecorderDatabaseSchema>(
        DATABASE_NAME,
        DATABASE_VERSION,
        {
          upgrade(db) {
            const upgradeDb = db as UpgradeDatabaseWithLegacySupport
            if (!db.objectStoreNames.contains(CHUNKS_STORE)) {
              const chunksStore = db.createObjectStore(CHUNKS_STORE, {
                keyPath: 'id',
                autoIncrement: true,
              })
              chunksStore.createIndex(BY_RECORDING_SEQUENCE_INDEX, [
                'recordingId',
                'sequenceNumber',
              ])
              chunksStore.createIndex(BY_RECORDING_TIMESTAMP_INDEX, [
                'recordingId',
                'timestamp',
              ])
            }

            if (upgradeDb.objectStoreNames.contains(LEGACY_RECORDINGS_STORE)) {
              upgradeDb.deleteObjectStore(LEGACY_RECORDINGS_STORE)
            }
          },
          blocked() {
            console.error('IndexedDB open is blocked')
          },
        }
      )
    }
    return this.dbPromise
  }

  public async saveChunk(
    blob: Blob,
    sequenceNumber: number,
    timestamp: number,
    recordingId = this.activeRecordingId
  ) {
    if (!recordingId) {
      throw new Error('No active recording id configured for chunk persistence')
    }

    const db = await this.openDatabase()
    const tx = db.transaction(CHUNKS_STORE, 'readwrite')

    const chunk: StoredChunk = {
      recordingId,
      sequenceNumber,
      timestamp,
      blob,
    }
    await tx.store.put(chunk)

    await tx.done
  }

  public async *getChunkStream(recordingId = this.activeRecordingId) {
    if (!recordingId) {
      throw new Error('No active recording id configured for chunk stream')
    }

    // Do not keep one transaction open across `yield`.
    // IndexedDB auto-commits transactions once control returns to the event loop,
    // which makes `cursor.continue()` fail on the next pull.
    let nextSequenceNumber = 0

    while (true) {
      const chunk = await this.getFirstChunkAtOrAfter(
        recordingId,
        nextSequenceNumber
      )
      if (!chunk) {
        return
      }

      yield chunk.blob
      nextSequenceNumber = chunk.sequenceNumber + 1
    }
  }

  public async deleteChunks(recordingId = this.activeRecordingId) {
    if (!recordingId) {
      throw new Error('No active recording id configured for deleteChunks')
    }

    const db = await this.openDatabase()
    const tx = db.transaction(CHUNKS_STORE, 'readwrite')
    const index = tx.store.index(BY_RECORDING_SEQUENCE_INDEX)
    let cursor = await index.openCursor(
      this.getRecordingSequenceRange(recordingId)
    )

    while (cursor) {
      await cursor.delete()
      cursor = await cursor.continue()
    }

    await tx.done
  }

  public async clearRecording(recordingId = this.activeRecordingId) {
    if (!recordingId) {
      throw new Error('No active recording id configured for clearRecording')
    }

    await this.deleteChunks(recordingId)

    if (this.activeRecordingId === recordingId) {
      this.activeRecordingId = null
    }
  }

  private async getFirstChunkAtOrAfter(
    recordingId: string,
    sequenceNumber: number
  ) {
    const db = await this.openDatabase()
    const tx = db.transaction(CHUNKS_STORE, 'readonly')
    const index = tx.store.index(BY_RECORDING_SEQUENCE_INDEX)
    const keyRange = IDBKeyRange.bound(
      [recordingId, sequenceNumber],
      [recordingId, Number.MAX_SAFE_INTEGER]
    )

    const cursor = await index.openCursor(keyRange)
    const chunk = (cursor?.value as StoredChunk | undefined) ?? null

    await tx.done
    return chunk
  }

  private getRecordingSequenceRange(recordingId: string) {
    return IDBKeyRange.bound(
      [recordingId, 0],
      [recordingId, Number.MAX_SAFE_INTEGER]
    )
  }
}
