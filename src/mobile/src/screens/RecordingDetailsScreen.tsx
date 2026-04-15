import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { SafeAreaView } from 'react-native-screens/experimental';
import type { RootStackParamList } from '@/navigation/types';

const formatDurationLabel = (durationSeconds: number) => {
  const minutes = Math.floor(durationSeconds / 60);
  const seconds = durationSeconds % 60;

  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(
    2,
    '0',
  )}`;
};

type RecordingDetailsRouteProp = RouteProp<
  RootStackParamList,
  'RecordingDetails'
>;

type StackNavigationProp = NativeStackNavigationProp<RootStackParamList>;

export default function RecordingDetailsScreen() {
  const route = useRoute<RecordingDetailsRouteProp>();
  const navigation = useNavigation<StackNavigationProp>();
  const { recording } = route.params;

  return (
    <SafeAreaView edges={{ top: true }} style={styles.container}>
      <View style={styles.content}>
        <Pressable style={styles.backButton} onPress={() => navigation.goBack()}>
          <Text style={styles.backButtonText}>Back</Text>
        </Pressable>

        <Text style={styles.title}>{recording.title}</Text>
        <Text style={styles.meta}>ID: {recording.id}</Text>
        <Text style={styles.meta}>Created: {recording.createdAt}</Text>
        <Text style={styles.meta}>
          Duration: {formatDurationLabel(recording.durationSeconds)}
        </Text>
        <Text style={styles.meta}>Source: {recording.kind}</Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F9FAFB',
  },
  content: {
    flex: 1,
    padding: 16,
    gap: 12,
  },
  backButton: {
    alignSelf: 'flex-start',
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: '#E5E7EB',
    borderRadius: 8,
  },
  backButtonText: {
    color: '#111827',
    fontWeight: '600',
  },
  title: {
    color: '#111827',
    fontSize: 22,
    fontWeight: '700',
  },
  meta: {
    color: '#374151',
    fontSize: 14,
  },
});
