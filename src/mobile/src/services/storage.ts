import { createMMKV } from 'react-native-mmkv';
import { recordingSchema, type Recording } from '../types/recording';
import {
  appSettingsSchema,
  type AppSettings,
} from '../types/settings';
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ApiUser } from '@/features/auth/api/ApiUser';
import { z } from 'zod/v4';

const storage = createMMKV({
  id: 'dictaphone-storage',
});

const RECORDINGS_KEY = 'recordings';
const SETTINGS_KEY = 'settings';
const USER_KEY = 'user';

const defaultSettings: AppSettings = {
  allowNetworkSync: false,
  language: 'en',
};

const apiUserSchema = z.object({
  id: z.string(),
  email: z.string(),
  full_name: z.string(),
  last_name: z.string(),
  language: z.enum(['fr-fr', 'en-us']),
  timezone: z.string(),
});

const recordingListSchema = z.array(recordingSchema);

const getRecordings = (): Recording[] => {
  const rawValue = storage.getString(RECORDINGS_KEY);
  if (!rawValue) {
    return [];
  }

  try {
    const parsed = JSON.parse(rawValue);
    const result = recordingListSchema.safeParse(parsed);
    return result.success ? result.data : [];
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
    const result = appSettingsSchema.safeParse(JSON.parse(rawValue));
    return result.success ? result.data : defaultSettings;
  } catch (error) {
    console.error('Failed to parse settings from storage', error);
    return defaultSettings;
  }
};

export const setSettings = (settings: AppSettings) => {
  storage.set(SETTINGS_KEY, JSON.stringify(settings));
};

export const getCachedUser = (): ApiUser | null => {
  const rawValue = storage.getString(USER_KEY);
  if (!rawValue) {
    return null;
  }

  try {
    const result = apiUserSchema.safeParse(JSON.parse(rawValue));
    return result.success ? result.data : null;
  } catch (error) {
    console.error('Failed to parse user from storage', error);
    return null;
  }
};

export const setCachedUser = (user: ApiUser) => {
  storage.set(USER_KEY, JSON.stringify(user));
};

export const clearCachedUser = () => {
  storage.remove(USER_KEY);
};
