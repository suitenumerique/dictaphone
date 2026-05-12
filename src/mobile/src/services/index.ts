import { createMMKV } from 'react-native-mmkv'
import type { StateStorage } from 'zustand/middleware'

export const storage = createMMKV({
  id: 'transcript-storage',
})

export const mmkvStorage: StateStorage = {
  setItem: (name, value) => {
    storage.set(name, value)
  },
  getItem: (name) => {
    return storage.getString(name) ?? null
  },
  removeItem: (name) => {
    storage.remove(name)
  },
}
