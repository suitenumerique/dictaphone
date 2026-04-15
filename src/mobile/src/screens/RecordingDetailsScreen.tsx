import React, { useCallback, useMemo } from 'react';
import {
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import type { RouteProp } from '@react-navigation/native';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '@/navigation/types';
import { useGetFile } from '@/features/files/api/getFile';
import { getMainAiJobs } from '@/features/ai-jobs/utils/getMainAiJobs';
import { useTranscript } from '@/features/ai-jobs/api/fetch';
import {
  buildTranscriptViewSegments,
  formatTimestamp,
} from '@/features/ai-jobs/utils/transcript';
import { useTranslation } from 'react-i18next';
import { useInsets } from '@/utils/useInsets';
import Lucide from '@react-native-vector-icons/lucide'; // @ts-expect-error
import DocsIcon from '@/assets/icons/docs.svg';
import RecordingMenu from '@/components/RecordingMenu';
import { intervalToDuration } from 'date-fns';

type RecordingDetailsRouteProp = RouteProp<
  RootStackParamList,
  'RecordingDetails'
>;

type StackNavigationProp = NativeStackNavigationProp<RootStackParamList>;

export default function RecordingDetailsScreen() {
  const route = useRoute<RecordingDetailsRouteProp>();
  const navigation = useNavigation<StackNavigationProp>();
  const { id } = route.params;
  const { t } = useTranslation();
  const insets = useInsets();

  const recordingQ = useGetFile(id);
  const recording = recordingQ.data;

  const { lastAiJobTranscript } = useMemo(
    () => getMainAiJobs(recordingQ.data?.ai_jobs),
    [recordingQ.data?.ai_jobs],
  );

  const transcriptQ = useTranscript(lastAiJobTranscript);
  const transcriptSegments = useMemo(
    () => buildTranscriptViewSegments(transcriptQ.data),
    [transcriptQ.data],
  );

  const numberOfParticipants = useMemo(() => {
    if (transcriptSegments.length === 0) {
      return null;
    } else {
      const speakers = new Set<string>(
        transcriptSegments.map(el => el.speaker).filter(Boolean) as string[],
      );
      return speakers.size;
    }
  }, [transcriptSegments]);

  const transcriptMarkdown = useMemo(() => {
    if (transcriptSegments.length === 0) {
      return null;
    }
    let out = `# ${recording!.title}\n\n`;
    transcriptSegments.forEach(segment => {
      out += `**${formatTimestamp(segment.start ?? -1)} · ${t(
        'transcript.speaker',
      )} ${segment.speaker}** ${segment.text} \n\n`;
    });
    return out;
  }, [recording, transcriptSegments, t]);

  const onDeleted = useCallback(() => {
    navigation.goBack();
  }, [navigation]);

  const onOpenInDocs = async () => {
    if (transcriptMarkdown) {
      await Share.share({
        message: transcriptMarkdown,
      });
    }
  };

  return (
    <View style={[styles.container, { paddingTop: insets.paddingTop }]}>
      <View style={styles.header}>
        <Pressable
          style={({ pressed }) => [
            styles.iconButton,
            pressed && styles.iconButtonPressed,
          ]}
          onPress={() => navigation.goBack()}
          hitSlop={10}
        >
          <Lucide name="arrow-left" size={26} color="#3E5DE7" />
        </Pressable>

        <Text style={styles.headerTitle} numberOfLines={1}>
          {recording ? recording.title : ''}
        </Text>

        {recording ? (
          <RecordingMenu
            fileId={recording.id}
            currentTitle={recording.title}
            onDeleted={onDeleted}
          />
        ) : (
          <View style={styles.iconButton} />
        )}
      </View>

      {recording && (
        <View style={styles.metaRow}>
          <View style={[styles.metaChip, { flexGrow: 1 }]}>
            <Lucide name="calendar-days" size={16} color="#6B7280" />
            <Text style={styles.metaChipText}>
              {t('shared.utils.formatDateTime', {
                value: recording.created_at,
              })}
              {/*{formatRelativeLabel(createdAt)}*/}
            </Text>
          </View>

          <View style={styles.metaChip}>
            <Lucide name="clock-3" size={16} color="#6B7280" />
            <Text style={styles.metaChipText}>
              {t('shared.utils.duration', {
                duration: intervalToDuration({
                  start: 0,
                  end: recording.duration_seconds * 1000,
                }),
              })}
              {/*{formatDurationLabel(durationSeconds || 0)}*/}
            </Text>
          </View>
          {transcriptSegments.length > 0 && (
            <View style={styles.metaChip}>
              <Lucide name="users" size={16} color="#6B7280" />
              <Text style={styles.metaChipText}>
                {numberOfParticipants ?? 0}
              </Text>
            </View>
          )}
        </View>
      )}

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={[
          styles.content,
          { paddingBottom: 90 + insets.paddingBottom },
        ]}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.transcriptContainer}>
          {transcriptSegments.length === 0 ? (
            <Text style={styles.emptyText}>{t('transcript.notAvailable')}</Text>
          ) : (
            transcriptSegments.map((segment, index) => (
              <Text
                key={`${segment.start ?? index}-${index}`}
                style={styles.paragraph}
              >
                <Text style={styles.timestamp}>
                  {formatTimestamp(segment.start ?? -1)}
                  {' · '}
                </Text>
                <Text style={styles.speaker}>
                  {t('transcript.speaker')} {segment.speaker}
                </Text>
                <Text style={styles.bodyText}> {segment.text}</Text>
              </Text>
            ))
          )}
        </View>
      </ScrollView>

      <View
        style={[
          styles.bottomBarContainer,
          { bottom: 12 + insets.paddingBottom },
        ]}
      >
        <View style={styles.bottomBar}>
          <Pressable style={styles.openButton} onPress={onOpenInDocs}>
            <DocsIcon />
            <Text style={styles.openButtonText}>Open in Docs</Text>
          </Pressable>

          <Pressable
            style={({ pressed }) => [
              styles.shareButton,
              pressed && styles.shareButtonPressed,
            ]}
            onPress={onOpenInDocs}
            hitSlop={8}
          >
            <Lucide name="share" size={22} color="#304DDF" />
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: 'white',
  },
  header: {
    height: 58,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  iconButton: {
    display: 'flex',
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconButtonPressed: {
    backgroundColor: '#E1E6EF',
  },
  headerTitle: {
    flex: 1,
    marginHorizontal: 8,
    textAlign: 'center',
    color: '#222631',
    fontSize: 14,
    lineHeight: 14,
    fontWeight: '700',
  },
  scroll: {
    flex: 1,
  },
  content: {
    paddingHorizontal: 16,
    paddingTop: 2,
    gap: 14,
  },
  metaRow: {
    display: 'flex',
    marginHorizontal: 8,
    flexDirection: 'row',
    borderRadius: 6,
    marginBottom: 12,
    overflow: 'hidden',
    backgroundColor: '#EEF1F6',
    borderWidth: 1,
    borderColor: 'white',
  },
  metaChip: {
    minHeight: 40,
    flexGrow: 0.9,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    borderRightWidth: 1,
    borderRightColor: 'white',
  },
  metaChipText: {
    color: '#6B7280',
    fontSize: 12,
    fontWeight: '500',
  },
  transcriptContainer: {
    paddingTop: 2,
  },
  paragraph: {
    fontSize: 12,
    lineHeight: 18,
    color: '#2B3448',
    marginBottom: 18,
  },
  timestamp: {
    color: '#0F172A',
    fontWeight: '800',
  },
  speaker: {
    color: '#0F172A',
    fontWeight: '800',
  },
  bodyText: {
    color: '#2B3448',
    fontWeight: '400',
  },
  emptyText: {
    color: '#6B7280',
    fontSize: 15,
    lineHeight: 22,
  },
  bottomBarContainer: {
    position: 'absolute',
    left: 0,
    right: 0,
    width: '100%',
    paddingHorizontal: 16,
    display: 'flex',
    alignItems: 'center',
  },
  bottomBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    maxWidth: 400,
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingVertical: 12,
    borderRadius: 8,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#D9DCE3',
    boxShadow: [
      {
        blurRadius: 15,
        spreadDistance: 5,
        color: '#D9DCE3',
        offsetX: 0,
        offsetY: 0,
      },
    ],
  },
  openButton: {
    flex: 1,
    height: 48,
    borderRadius: 8,
    backgroundColor: '#4760E8',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    shadowColor: '#2F47D0',
    shadowOpacity: 0.18,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },
  openButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: 'medium',
  },
  shareButton: {
    width: 52,
    height: 48,
    borderRadius: 8,
    backgroundColor: '#DAE2FF',
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
  },
  shareButtonPressed: {
    backgroundColor: '#e5ebfe',
  },
});
