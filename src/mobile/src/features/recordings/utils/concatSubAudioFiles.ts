import { concatAudioFiles } from 'react-native-audio-api'
import {
  deleteLocalRecordingFile,
  getFileName,
} from '@/utils/localRecordingFile'

export const FILENAME_PREFIX_SEPARATOR = '--rotate-sep--'

export async function concatSubAudioFiles<T extends { path: string }>(
  files: [T, ...T[]]
): Promise<[string | null, T[]]> {
  const baseFileName = getFileName(files[0].path)
    .split(FILENAME_PREFIX_SEPARATOR)[0]
    .split('.')[0]
  const concatenatedFilePath = [
    ...files[0].path.split('/').slice(0, -1),
    `${baseFileName}-concat.m4a`,
  ].join('/')

  console.info(
    `Concatenating ${files.length} audio files to ${concatenatedFilePath}:`
  )
  let outputPath: string | null = null
  let used: T[] = files
  try {
    outputPath = await concatAudioFiles(
      used.map((file) => file.path),
      concatenatedFilePath
    )
  } catch (e) {
    console.warn(
      'Failed to concatenate audio files, likely due to that last sub file being invalid when the app hard crashes, trying to concat all but the last one',
      e
    )
    if (files.length > 1) {
      used = files.slice(0, -1)
      outputPath = await concatAudioFiles(
        used.map((file) => file.path),
        concatenatedFilePath
      )
    }
  }

  console.info('Concatenation done, deleting sub audio files')
  await Promise.all(
    files.map(async (file) => {
      try {
        await deleteLocalRecordingFile(file.path)
      } catch (error) {
        console.warn(`Failed to delete source segment ${file.path}:`, error)
      }
    })
  )

  return [outputPath, used]
}
