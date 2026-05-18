import { StoredChunk } from '@/features/recordings/recorder/types.ts'

const DATABASE_NAME = 'audio-recorder'
const DATABASE_VERSION = 2
const CHUNKS_STORE = 'chunks'

type IDBDatabaseWithStores = IDBDatabase

const openCursorRequest = (
  source: IDBObjectStore | IDBIndex,
  query?: IDBValidKey | IDBKeyRange
) =>
  new Promise<IDBCursorWithValue | null>((resolve, reject) => {
    const request = source.openCursor(query)
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })

const txDone = (transaction: IDBTransaction) =>
  new Promise<void>((resolve, reject) => {
    transaction.oncomplete = () => resolve()
    transaction.onerror = () => reject(transaction.error)
    transaction.onabort = () => reject(transaction.error)
  })

/**
 * IndexedDB-based chunk store for audio recordings.
 * Helps to keep memory usage low and data safe in regards to browser crashes, etc.
 *
 * Was mostly LLM generated.
 */
export class IndexedDbChunkStore {
  private dbPromise: Promise<IDBDatabaseWithStores> | null = null
  private activeRecordingId: string | null = null

  public setActiveRecording(recordingId: string) {
    this.activeRecordingId = recordingId
  }

  public getActiveRecordingId() {
    return this.activeRecordingId
  }

  public async openDatabase() {
    if (this.dbPromise) {
      return this.dbPromise
    }

    this.dbPromise = new Promise<IDBDatabaseWithStores>((resolve, reject) => {
      const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION)

      request.onupgradeneeded = () => {
        const db = request.result

        if (!db.objectStoreNames.contains(CHUNKS_STORE)) {
          const chunksStore = db.createObjectStore(CHUNKS_STORE, {
            keyPath: 'id',
            autoIncrement: true,
          })
          chunksStore.createIndex(
            'byRecordingSequence',
            ['recordingId', 'sequenceNumber'],
            {
              unique: true,
            }
          )
          chunksStore.createIndex('byRecordingTimestamp', [
            'recordingId',
            'timestamp',
          ])
        }

        if (db.objectStoreNames.contains('recordings')) {
          db.deleteObjectStore('recordings')
        }
      }

      request.onsuccess = () => {
        const db = request.result
        db.onversionchange = () => db.close()
        resolve(db)
      }
      request.onerror = () => reject(request.error)
      request.onblocked = () => reject(new Error('IndexedDB open is blocked'))
    })

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
    const chunksStore = tx.objectStore(CHUNKS_STORE)

    const chunk: StoredChunk = {
      recordingId,
      sequenceNumber,
      timestamp,
      blob,
    }
    chunksStore.put(chunk)

    await txDone(tx)
  }

  public async *getChunkStream(recordingId = this.activeRecordingId) {
    if (!recordingId) {
      throw new Error('No active recording id configured for chunk stream')
    }

    const db = await this.openDatabase()
    const tx = db.transaction(CHUNKS_STORE, 'readonly')
    const index = tx.objectStore(CHUNKS_STORE).index('byRecordingSequence')
    const keyRange = IDBKeyRange.bound(
      [recordingId, 0],
      [recordingId, Number.MAX_SAFE_INTEGER]
    )
    // Cursor iteration avoids materializing all chunks in memory (no getAll()).
    let cursor = await openCursorRequest(index, keyRange)

    while (cursor) {
      const chunk = cursor.value as StoredChunk
      yield chunk.blob
      cursor = await new Promise<IDBCursorWithValue | null>(
        (resolve, reject) => {
          cursor!.continue()
          cursor!.request.onsuccess = () => resolve(cursor!.request.result)
          cursor!.request.onerror = () => reject(cursor!.request.error)
        }
      )
    }
    await txDone(tx)
  }

  public async deleteChunks(recordingId = this.activeRecordingId) {
    if (!recordingId) {
      throw new Error('No active recording id configured for deleteChunks')
    }

    const db = await this.openDatabase()
    const tx = db.transaction(CHUNKS_STORE, 'readwrite')
    const index = tx.objectStore(CHUNKS_STORE).index('byRecordingSequence')
    const range = IDBKeyRange.bound(
      [recordingId, 0],
      [recordingId, Number.MAX_SAFE_INTEGER]
    )
    let cursor = await openCursorRequest(index, range)

    while (cursor) {
      cursor.delete()
      cursor = await new Promise<IDBCursorWithValue | null>(
        (resolve, reject) => {
          cursor!.continue()
          cursor!.request.onsuccess = () => resolve(cursor!.request.result)
          cursor!.request.onerror = () => reject(cursor!.request.error)
        }
      )
    }
    await txDone(tx)
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
}
