import React, { useCallback, useMemo } from 'react';
import {
  ActivityIndicator,
  Linking,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  View,
} from 'react-native';
import type { RouteProp } from '@react-navigation/native';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '@/navigation/types';
import { useGetFile } from '@/features/files/api/getFile';
import { getMainAiJobs } from '@/features/ai-jobs/utils/getMainAiJobs';
import {
  useOpenInDocsMutation,
  useTranscript,
} from '@/features/ai-jobs/api/fetch';
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
import { InAppBrowser } from 'react-native-inappbrowser-reborn';
import { AppText } from '@/components/AppText';
import { colors } from '@/components/colors';

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

  const openInDocs = useOpenInDocsMutation();
  const handleOpenInDocs = useCallback(() => {
    if (lastAiJobTranscript?.id && lastAiJobTranscript.status === 'success') {
      openInDocs.mutate(lastAiJobTranscript, {
        onSuccess: async res => {
          const isAvailable = await InAppBrowser.isAvailable();
          if (isAvailable) {
            await InAppBrowser.open(res.doc_url, {
              // iOS Properties
              preferredBarTintColor: colors.secondary,
              preferredControlTintColor: 'white',
              readerMode: false,
              animated: true,
              modalPresentationStyle: 'fullScreen',
              modalTransitionStyle: 'coverVertical',
              modalEnabled: true,
              enableBarCollapsing: false,
              // Android Properties
              showTitle: false,
              toolbarColor: colors.secondary,
              secondaryToolbarColor: 'black',
              navigationBarColor: 'black',
              navigationBarDividerColor: 'white',
              enableUrlBarHiding: true,
            });
          } else {
            await Linking.openURL(res.doc_url);
          }
        },
      });
    }
  }, [lastAiJobTranscript, openInDocs]);

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

  const handleShareMarkdown = useCallback(async () => {
    if (transcriptMarkdown) {
      await Share.share({
        message: transcriptMarkdown,
      });
    }
  }, [transcriptMarkdown]);

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
          <Lucide name="arrow-left" size={26} color={colors.primary} />
        </Pressable>

        <AppText
          variant="heading"
          align="center"
          numberOfLines={1}
          style={styles.headerTitle}
        >
          {recording ? recording.title : ''}
        </AppText>

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
            <Lucide
              name="calendar-days"
              size={16}
              color={colors.neutralSecondary}
            />
            <AppText
              variant="subtitle"
              size="sm"
              color={colors.neutralSecondary}
            >
              {t('shared.utils.formatDateTime', {
                value: recording.created_at,
              })}
              {/*{formatRelativeLabel(createdAt)}*/}
            </AppText>
          </View>

          <View style={styles.metaChip}>
            <Lucide name="clock-3" size={16} color={colors.neutralSecondary} />
            <AppText
              variant="subtitle"
              size="sm"
              color={colors.neutralSecondary}
            >
              {t('shared.utils.duration', {
                duration: intervalToDuration({
                  start: 0,
                  end: recording.duration_seconds * 1000,
                }),
              })}
              {/*{formatDurationLabel(durationSeconds || 0)}*/}
            </AppText>
          </View>
          {transcriptSegments.length > 0 && (
            <View style={styles.metaChip}>
              <Lucide name="users" size={16} color={colors.neutralSecondary} />
              <AppText
                variant="subtitle"
                size="sm"
                color={colors.neutralSecondary}
              >
                {numberOfParticipants ?? 0}
              </AppText>
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
          {transcriptQ.isPending ? (
            <ActivityIndicator />
          ) : transcriptSegments.length === 0 ? (
            <AppText variant="muted" size="md" color={colors.neutralTertiary}>
              {t('transcript.notAvailable')}
            </AppText>
          ) : (
            transcriptSegments.map((segment, index) => (
              <AppText
                variant="body"
                size="sm"
                key={`${segment.start ?? index}-${index}`}
                style={styles.paragraph}
              >
                <AppText variant="bodyBold">
                  {formatTimestamp(segment.start ?? -1)}
                  {' · '}
                </AppText>
                <AppText variant="bodyBold">
                  {t('transcript.speaker')} {segment.speaker}
                </AppText>
                <AppText variant="body">
                  {'  '}
                  {segment.text}
                </AppText>
              </AppText>
            ))
          )}
        </View>
      </ScrollView>

      {transcriptSegments.length > 0 && (
        <View
          style={[
            styles.bottomBarContainer,
            { bottom: 12 + insets.paddingBottom },
          ]}
        >
          <View style={styles.bottomBar}>
            <Pressable
              style={({ pressed }) => [
                styles.openInDocsButton,
                pressed && styles.openInDocsButtonPressed,
                !lastAiJobTranscript?.docs_app_id &&
                  styles.openInDocsButtonDisabled,
              ]}
              disabled={!lastAiJobTranscript?.docs_app_id}
              onPress={handleOpenInDocs}
            >
              <DocsIcon />
              <AppText style={styles.openInDocsButtonText}>
                Open in Docs
              </AppText>
            </Pressable>

            <Pressable
              style={({ pressed }) => [
                styles.shareButton,
                pressed && styles.shareButtonPressed,
              ]}
              onPress={handleShareMarkdown}
              hitSlop={8}
            >
              <Lucide name="share" size={22} color="#304DDF" />
            </Pressable>
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.backgroundBase,
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
    backgroundColor: colors.backgroundSubtlePressed,
  },
  headerTitle: {
    flexShrink: 1,
    marginHorizontal: 8,
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
    backgroundColor: colors.backgroundNeutralTertiary,
    borderWidth: 1,
    borderColor: colors.backgroundBase,
  },
  metaChip: {
    minHeight: 40,
    flexGrow: 0.9,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    borderRightWidth: 1,
    borderRightColor: colors.backgroundBase,
  },
  transcriptContainer: {
    paddingTop: 2,
  },
  paragraph: {
    marginBottom: 18,
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
    backgroundColor: colors.backgroundBase,
    borderWidth: 1,
    borderColor: colors.surfacePrimary,
    boxShadow: [
      {
        blurRadius: 15,
        spreadDistance: 5,
        color: colors.shadowDefault,
        offsetX: 0,
        offsetY: 0,
      },
    ],
  },
  openInDocsButton: {
    flex: 1,
    height: 48,
    borderRadius: 8,
    backgroundColor: colors.primary,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
  },
  openInDocsButtonDisabled: {
    backgroundColor: '#97989b',
    shadowColor: '#97989b',
  },
  openInDocsButtonPressed: {
    backgroundColor: '#304DDF',
  },
  openInDocsButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: 'medium',
  },
  shareButton: {
    width: 52,
    height: 48,
    borderRadius: 8,
    backgroundColor: colors.secondary,
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
  },
  shareButtonPressed: {
    backgroundColor: colors.secondaryPressed,
  },
});
