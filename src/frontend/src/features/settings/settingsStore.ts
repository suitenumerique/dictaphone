import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

export const TRANSCRIPTION_LANGUAGES = ['fr', 'en', 'nl', 'de'] as const
export type TranscriptionLanguage = (typeof TRANSCRIPTION_LANGUAGES)[number]

type SettingsState = {
  newTranscriptionLanguage: TranscriptionLanguage | null
  setNewTranscriptionLanguage: (language: TranscriptionLanguage) => void
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      newTranscriptionLanguage: null,
      setNewTranscriptionLanguage: (language) =>
        set({ newTranscriptionLanguage: language }),
    }),
    {
      name: 'settings-store',
      storage: createJSONStorage(() => localStorage),
    }
  )
)
