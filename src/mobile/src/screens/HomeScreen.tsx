import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { AudioRecorder } from '../components/AudioRecorder';
import { addRecording } from '../services/storage';
import type { Recording } from '../types/recording';
import uuid from 'react-native-uuid';

const formatDurationLabel = (durationMs: number) => {
  const totalSeconds = Math.max(0, Math.floor(durationMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
};

export default function HomeScreen() {
  const { t } = useTranslation();

  const handleRecordingComplete = ({
    createdAt,
    duration,
    filePath,
  }: Omit<Recording, 'id' | 'name' | 'synced'>) => {
    const name = t('home.recordingName', { duration: formatDurationLabel(duration) });
    addRecording({
      createdAt,
      duration,
      filePath,
      id: String(uuid.v4()),
      name,
      synced: false,
    });
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>{t('home.title')}</Text>
      <AudioRecorder onRecordingComplete={handleRecordingComplete} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'flex-start',
    alignItems: 'center',
    paddingTop: 48,
    paddingHorizontal: 24,
    backgroundColor: '#F9FAFB',
  },
  title: {
    fontSize: 36,
    fontWeight: '800',
    color: '#111827',
    marginBottom: 8,
  },
});
