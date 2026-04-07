import { createMMKV } from 'react-native-mmkv';
import type { Recording } from '../types/recording';
import type { AppSettings, AppLanguage } from '../types/settings';

const storage = createMMKV({
  id: 'dictaphone-storage',
});

const RECORDINGS_KEY = 'recordings';
const SETTINGS_KEY = 'settings';

const defaultSettings: AppSettings = {
  allowNetworkSync: false,
  language: 'en',
};

const isValidLanguage = (language: string): language is AppLanguage => {
  return language === 'en' || language === 'fr';
};

const normalizeRecording = (value: unknown): Recording | null => {
  if (!value || typeof value !== 'object') {
    return null;
  }

  const raw = value as Partial<Recording>;
  if (
    typeof raw.id !== 'string' ||
    typeof raw.name !== 'string' ||
    typeof raw.filePath !== 'string' ||
    typeof raw.createdAt !== 'string' ||
    typeof raw.duration !== 'number'
  ) {
    return null;
  }

  return {
    createdAt: raw.createdAt,
    duration: raw.duration,
    filePath: raw.filePath,
    id: raw.id,
    name: raw.name,
    synced: typeof raw.synced === 'boolean' ? raw.synced : false,
  };
};

export const getRecordings = (): Recording[] => {
  const rawValue = storage.getString(RECORDINGS_KEY);
  if (!rawValue) {
    return [];
  }

  try {
    const parsed = JSON.parse(rawValue);
    if (!Array.isArray(parsed)) {
      return [];
    }

    return parsed
      .map(normalizeRecording)
      .filter((recording): recording is Recording => recording !== null);
  } catch (error) {
    console.error('Failed to parse recordings from storage', error);
    return [];
  }
};

export const setRecordings = (recordings: Recording[]) => {
  storage.set(RECORDINGS_KEY, JSON.stringify(recordings));
};

export const addRecording = (recording: Recording) => {
  const nextRecordings = [recording, ...getRecordings()];
  setRecordings(nextRecordings);
  return nextRecordings;
};

export const deleteRecording = (recordingId: string) => {
  const nextRecordings = getRecordings().filter(recording => recording.id !== recordingId);
  setRecordings(nextRecordings);
  return nextRecordings;
};

export const getSettings = (): AppSettings => {
  const rawValue = storage.getString(SETTINGS_KEY);
  if (!rawValue) {
    return defaultSettings;
  }

  try {
    const parsed = JSON.parse(rawValue) as Partial<AppSettings>;
    const language = parsed.language;
    return {
      allowNetworkSync: Boolean(parsed.allowNetworkSync),
      language: typeof language === 'string' && isValidLanguage(language) ? language : 'en',
    };
  } catch (error) {
    console.error('Failed to parse settings from storage', error);
    return defaultSettings;
  }
};

export const setSettings = (settings: AppSettings) => {
  storage.set(SETTINGS_KEY, JSON.stringify(settings));
};
