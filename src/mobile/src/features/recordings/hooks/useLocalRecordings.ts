import { useMemo } from 'react';
import { useRecordingsStore } from '@/services/storage';

export const useLocalRecordings = () => {
  const { recordings, addRecording, updateRecording } = useRecordingsStore();

  return useMemo(
    () => ({
      recordings,
      addRecording,
      updateRecording,
    }),
    [recordings, addRecording, updateRecording],
  );
};
