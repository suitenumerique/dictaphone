import React from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { AudioRecorder } from '../components/AudioRecorder';
import type { Recording } from '../types/recording';
import { useLocalRecordings } from '@/features/recordings/hooks/useLocalRecordings';
import uuid from 'react-native-uuid';
import { formatDuration } from '@/features/recordings/utils/formatDuration';
import { SafeAreaView } from 'react-native-screens/experimental';

export default function HomeScreen() {
  const { t } = useTranslation();
  const { addRecording, isUploading } = useLocalRecordings();

  const handleRecordingComplete = ({
    createdAt,
    durationMs,
    filePath,
  }: Omit<Recording, 'id' | 'name' | 'uploadingStatus'>) => {
    const name = t('home.recordingName', {
      duration: formatDuration(durationMs),
    });
    addRecording({
      createdAt,
      durationMs,
      filePath,
      name,
      id: uuid.v4(),
      uploadingStatus: 'to_upload',
    });
  };

  return (
    <SafeAreaView edges={{ bottom: true, top: true }} style={styles.container}>
      <Text style={styles.title}>{t('home.title')}</Text>
      <View style={styles.recorderContainer}>
        <AudioRecorder onRecordingComplete={handleRecordingComplete} />
        <View
          style={{
            ...styles.uploadingContainer,
            ...(isUploading ? { opacity: 1 } : { opacity: 0 }),
          }}
        >
          <ActivityIndicator size="small" color="#1D4ED8" />
          <Text style={styles.uploadingText}>{t('recordings.uploading')}</Text>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'flex-start',
    alignItems: 'center',
    paddingTop: 72,
    paddingHorizontal: 24,
    backgroundColor: '#F9FAFB',
  },
  title: {
    fontSize: 36,
    fontWeight: '800',
    color: '#111827',
    marginBottom: 8,
  },
  recorderContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  uploadingContainer: {
    marginTop: 16,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderRadius: 12,
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  uploadingText: {
    color: '#1F2937',
    fontWeight: '600',
    fontSize: 14,
  },
});
