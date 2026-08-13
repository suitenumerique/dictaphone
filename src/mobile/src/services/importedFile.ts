import { getAudioDuration } from 'react-native-audio-api'
import {
  errorCodes,
  isKnownType,
  isErrorWithCode,
  pick,
  types,
  type DocumentPickerResponse,
} from '@react-native-documents/picker'
import { useConfigStore } from '@/services/configStore'
import { useRecordingsStore, useSettingsStore } from '@/services/storage'
import { deleteLocalRecordingFile } from '@/utils/localRecordingFile'
import { copyExternalFile, type ExternalFileCopy } from '@/utils/fileUpload'

export type ImportedFileInput = {
  uri: string
  name?: string | null
  type?: string | null
  size?: number | null
}

export type ImportedFileErrorCode =
  | 'unsupported_type'
  | 'too_large'
  | 'too_long'
  | 'unrecognized_audio'
  | 'generic'

export class ImportedFileError extends Error {
  constructor(public readonly code: ImportedFileErrorCode) {
    super(code)
    this.name = 'ImportedFileError'
  }
}

const extensionFromName = (name: string): string => {
  const match = name.match(/(\.[^./\\]+)$/)
  return match?.[1]?.toLowerCase() ?? ''
}

const titleFromName = (name: string): string => {
  const title = name.replace(/\.[^./\\]+$/, '').trim()
  return title || name
}

const normalizeMimeType = (type: string | null | undefined): string =>
  type?.split(';', 1)[0].trim().toLowerCase() ?? ''

const mimeTypeFromExtension = (extension: string): string => {
  switch (extension) {
    case '.m4a':
    case '.mp4':
      return 'audio/mp4'
    case '.mp3':
      return 'audio/mpeg'
    case '.wav':
      return 'audio/wav'
    case '.ogg':
      return 'audio/ogg'
    case '.opus':
      return 'audio/opus'
    case '.flac':
      return 'audio/flac'
    case '.aac':
      return 'audio/aac'
    case '.webm':
    case '.weba':
      return 'audio/webm'
    default:
      return ''
  }
}

const getConfig = () => useConfigStore.getState().config?.audio_recording

const isNativeFileTooLargeError = (error: unknown): boolean =>
  typeof error === 'object' &&
  error !== null &&
  'code' in error &&
  error.code === 'FILE_TOO_LARGE'

const getAllowedPickerTypes = (): string[] => {
  const allowedMimetypes = getConfig()?.allowed_mimetypes ?? []
  const allowedExtensions = getConfig()?.allowed_extensions ?? []

  if (allowedMimetypes.length === 0 && allowedExtensions.length === 0) {
    return [types.audio]
  }

  const extensionTypes = allowedExtensions
    .map((extension) => extension.replace(/^\./, ''))
    .map((extension) => isKnownType({ kind: 'extension', value: extension }))
    .filter((result) => result.isKnown)
    .map((result) => result.UTType ?? result.mimeType)
    .filter((type): type is string => Boolean(type))

  const mimeTypes = allowedMimetypes
    .map((type) => normalizeMimeType(type))
    .filter(Boolean)
    .map((mimeType) => isKnownType({ kind: 'mimeType', value: mimeType }))
    .filter((result) => result.isKnown)
    .map((result) => result.UTType ?? result.mimeType)
    .filter((type): type is string => Boolean(type))

  const platformTypes = [...extensionTypes, ...mimeTypes]
  return [...new Set(platformTypes.length > 0 ? platformTypes : [types.audio])]
}

const validateImportedFile = (
  file: ImportedFileInput,
  copied?: ExternalFileCopy
) => {
  const config = getConfig()
  const name = file.name?.trim() || copied?.name.trim() || 'audio-file.m4a'
  const extension = extensionFromName(name)
  const mimeType =
    normalizeMimeType(file.type) || mimeTypeFromExtension(extension)

  if (config) {
    const allowedExtensions = new Set(
      config.allowed_extensions.map((value) => value.toLowerCase())
    )
    const allowedMimetypes = new Set(
      config.allowed_mimetypes.map((value) => normalizeMimeType(value))
    )
    const extensionAllowed = allowedExtensions.has(extension)
    const mimeTypeAllowed = allowedMimetypes.has(mimeType)
    if (!extensionAllowed && !mimeTypeAllowed) {
      throw new ImportedFileError('unsupported_type')
    }

    const size = copied?.size ?? file.size ?? 0
    if (size > config.max_size) {
      throw new ImportedFileError('too_large')
    }
  }

  if (!config && !mimeType.startsWith('audio/')) {
    throw new ImportedFileError('unsupported_type')
  }

  return { name, extension, mimeType }
}

export const queueImportedFile = async (
  file: ImportedFileInput
): Promise<void> => {
  validateImportedFile(file)
  let copied: ExternalFileCopy | undefined

  try {
    const maxSize = file.size ?? getConfig()?.max_size ?? 0
    copied = await copyExternalFile(file.uri, file.name?.trim() ?? '', maxSize)
    const prepared = validateImportedFile(file, copied)
    const durationSeconds = await getAudioDuration(copied.path)
    const maxDurationSeconds = getConfig()?.max_duration_seconds ?? 0

    if (!Number.isFinite(durationSeconds) || durationSeconds <= 0) {
      throw new ImportedFileError('unrecognized_audio')
    }
    if (maxDurationSeconds > 0 && durationSeconds > maxDurationSeconds) {
      throw new ImportedFileError('too_long')
    }

    const settings = useSettingsStore.getState()
    const language =
      settings.newTranscriptionLanguage ??
      (settings.settings.language === 'en' ? 'en' : 'fr')

    useRecordingsStore.getState().addRecording({
      created_at: new Date().toISOString(),
      duration_seconds: durationSeconds,
      filePath: copied.path,
      title: titleFromName(prepared.name),
      id: `import-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      language,
      uploadingStatus: 'to_upload',
      source: 'mobile_file_upload',
      fileName: prepared.name,
      mimeType: file.type || prepared.mimeType,
    })
  } catch (error) {
    if (copied) {
      try {
        await deleteLocalRecordingFile(copied.path)
      } catch (cleanupError) {
        console.warn('Failed to clean up imported file:', cleanupError)
      }
    }
    throw isNativeFileTooLargeError(error)
      ? new ImportedFileError('too_large')
      : error
  }
}

export const pickAndQueueFile = async (): Promise<void> => {
  let result: DocumentPickerResponse
  try {
    const picked = await pick({
      mode: 'import',
      type: getAllowedPickerTypes(),
      allowMultiSelection: false,
      allowVirtualFiles: false,
    })
    result = picked[0]
  } catch (error) {
    if (
      isErrorWithCode(error) &&
      error.code === errorCodes.OPERATION_CANCELED
    ) {
      return
    }
    throw error
  }

  if (result.error || !result.uri) {
    throw new ImportedFileError('unrecognized_audio')
  }
  if (result.hasRequestedType === false) {
    throw new ImportedFileError('unsupported_type')
  }

  await queueImportedFile({
    uri: result.uri,
    name: result.name,
    type: result.type,
    size: result.size,
  })
}
