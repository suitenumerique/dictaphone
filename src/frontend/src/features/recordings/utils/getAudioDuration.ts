/**
 * Retrieves the duration of an audio file in seconds.
 *
 * @param {File} file - The audio file whose duration is to be determined.
 * @return {Promise<number | null>} A promise that resolves to the duration of the audio in seconds, or null if the file is not an audio file or the duration could not be determined.
 */
export async function getAudioDuration(file: File): Promise<number | null> {
  return new Promise((resolve) => {
    const audio = document.createElement('audio')
    const objectUrl = URL.createObjectURL(file)

    const cleanup = () => {
      URL.revokeObjectURL(objectUrl)
      audio.removeAttribute('src')
      audio.load()
    }

    audio.preload = 'metadata'
    audio.onloadedmetadata = () => {
      const duration = Number.isFinite(audio.duration) ? audio.duration : null
      cleanup()
      resolve(duration)
    }
    audio.onerror = () => {
      cleanup()
      resolve(null)
    }
    audio.src = objectUrl
  })
}
