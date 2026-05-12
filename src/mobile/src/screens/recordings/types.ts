import type { ApiFileItem } from '@/features/files/api/types'
import type { LocalRecording } from '@/types/localRecording'

export type RemoteRecording = ApiFileItem & { kind: 'remote' }

export type LocalOrRemoteRecording =
  | RemoteRecording
  | (LocalRecording & { kind: 'local' })
  | { kind: 'fake'; id: string }
