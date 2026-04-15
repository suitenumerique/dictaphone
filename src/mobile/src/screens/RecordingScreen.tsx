import React from 'react';
import { StyleSheet, View } from 'react-native';
import { AudioRecorder } from '../components/AudioRecorder';
import { SafeAreaView } from 'react-native-screens/experimental';

export default function RecordScreen() {
  return (
    <SafeAreaView edges={{ bottom: true, top: true }} style={styles.container}>
      <View style={styles.recorderContainer}>
        <AudioRecorder />
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
    marginBottom: 8,
  },
  recorderContainer: {
    flex: 1,
    width: '100%',
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
