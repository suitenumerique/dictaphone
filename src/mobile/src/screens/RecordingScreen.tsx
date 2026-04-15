import React from 'react';
import { StyleSheet, View } from 'react-native';
import { AudioRecorder } from '../components/AudioRecorder';
import { useInsets } from '@/utils/useInsets';

export default function RecordScreen() {
  const insets = useInsets()

  return (
    <View style={[styles.container, insets]}>
      <View style={styles.recorderContainer}>
        <AudioRecorder />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    justifyContent: 'flex-start',
    alignItems: 'center',
  },
  title: {
    marginBottom: 8,
  },
  recorderContainer: {
    flex: 1,
    width: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 20,
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
