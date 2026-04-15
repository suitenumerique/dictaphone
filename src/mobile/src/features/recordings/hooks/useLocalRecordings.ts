import { useEffect, useMemo, useRef, useState } from 'react';
import { useNetInfo } from '@react-native-community/netinfo';
import { useCreateFile } from '@/features/files/api/createFile';
import { useRecordingsStore } from '@/services/storage';

export const useLocalRecordings = () => {
  const netInfo = useNetInfo();
  const createFileMutation = useCreateFile();

  const { recordings, addRecording, deleteRecording, updateRecording } =
    useRecordingsStore();
  const [recordingIdBeingUploaded, setRecordingIdBeingUploaded] = useState<
    string | null
  >(null);
  const isUploading = useRef<boolean>(false);

  const isOnline =
    netInfo.isConnected === true && netInfo.isInternetReachable !== false;

  useEffect(() => {
    if (recordingIdBeingUploaded === null && !isUploading.current) {
      const recordingToUpload = recordings.find(
        recording => recording.uploadingStatus === 'to_upload',
      );
      if (recordingToUpload && isOnline) {
        isUploading.current = true;
        setRecordingIdBeingUploaded(recordingToUpload.id);
        updateRecording(recordingToUpload.id, { uploadingStatus: 'uploading' });
        createFileMutation.mutate(
          {
            durationSeconds: Math.max(
              1,
              Math.round(recordingToUpload.durationMs / 1000),
            ),
            file: {
              name: `${recordingToUpload.name}.m4a`,
              type: 'audio/mp4',
              uri: recordingToUpload.filePath,
            },
          },
          {
            onError: () => {
              updateRecording(recordingToUpload.id, {
                uploadingStatus: 'failed',
              });
              setRecordingIdBeingUploaded(null);
            },
            onSuccess: () => {
              deleteRecording(recordingToUpload.id);
              setRecordingIdBeingUploaded(null);
            },
            onSettled: () => {
              isUploading.current = false;
              setRecordingIdBeingUploaded(null);
            },
          },
        );
      }
    }
  }, [
    createFileMutation,
    deleteRecording,
    isOnline,
    recordingIdBeingUploaded,
    recordings,
    updateRecording,
  ]);

  return useMemo(
    () => ({
      recordings,
      addRecording,
      updateRecording,
      recordingIdBeingUploaded,
      isUploading: recordingIdBeingUploaded !== null,
    }),
    [recordings, addRecording, updateRecording, recordingIdBeingUploaded],
  );
};
