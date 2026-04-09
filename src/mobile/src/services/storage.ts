import { createMMKV } from 'react-native-mmkv';
import type { Recording } from '../types/recording';
import type { AppLanguage, AppSettings } from '../types/settings';
import { useCallback, useEffect, useMemo, useState } from 'react';

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
    typeof raw.durationMs !== 'number' || typeof raw.uploadingStatus !== 'string'
  ) {
    return null;
  }

  return {
    createdAt: raw.createdAt,
    durationMs: raw.durationMs,
    filePath: raw.filePath,
    id: raw.id,
    name: raw.name,
    uploadingStatus: raw.uploadingStatus ?? "to_upload",
  };
};

const getRecordings = (): Recording[] => {
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

const storeRecordings = (recordings: Recording[]) => {
  storage.set(RECORDINGS_KEY, JSON.stringify(recordings));
};

function _resetUploadState() {
  storeRecordings(
    getRecordings().map(recording => ({ ...recording, isUploading: false })),
  );
}
// We reset the upload state to false for all recordings on app start
_resetUploadState();

export const useRecordings = () => {
  const [recordings, setRecorings] = useState<Recording[]>(getRecordings());
  useEffect(() => {
    storeRecordings(recordings);
  }, [recordings]);

  const addRecording = useCallback((recording: Recording) => {
    setRecorings(prev => [recording, ...prev]);
  }, []);

  const deleteRecording = useCallback((recordingId: string) => {
    setRecorings(prev =>
      prev.filter(recording => recording.id !== recordingId),
    );
  }, []);

  const updateRecording = useCallback(
    (id: string, data: Partial<Omit<Recording, 'id'>>) => {
      setRecorings(prev =>
        prev.map(recording =>
          recording.id === id ? { ...recording, ...data } : recording,
        ),
      );
    },
    [],
  );

  return useMemo(
    () => ({
      recordings,
      addRecording,
      deleteRecording,
      updateRecording,
    }),
    [addRecording, deleteRecording, recordings, updateRecording],
  );
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
      language:
        typeof language === 'string' && isValidLanguage(language)
          ? language
          : 'en',
    };
  } catch (error) {
    console.error('Failed to parse settings from storage', error);
    return defaultSettings;
  }
};

export const setSettings = (settings: AppSettings) => {
  storage.set(SETTINGS_KEY, JSON.stringify(settings));
};
