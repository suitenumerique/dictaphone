import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ActivityIndicator,
  Alert,
  Linking,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  View,
} from 'react-native'
import type { RouteProp } from '@react-navigation/native'
import { useNavigation, useRoute } from '@react-navigation/native'
import type { NativeStackNavigationProp } from '@react-navigation/native-stack'
import type { RootStackParamList } from '@/navigation/types'
import { useGetFile } from '@/features/files/api/getFile'
import { getMainAiJobs } from '@/features/ai-jobs/utils/getMainAiJobs'
import {
  useOpenInDocsMutation,
  useTranscript,
} from '@/features/ai-jobs/api/fetch'
import {
  buildTranscriptViewSegments,
  formatTimestamp,
} from '@/features/ai-jobs/utils/transcript'
import { useTranslation } from 'react-i18next'
import { useInsets } from '@/utils/useInsets'
import Lucide from '@react-native-vector-icons/lucide' // @ts-expect-error Icon
import DocsIcon from '@/assets/icons/docs.svg'
import RecordingMenu from '@/components/RecordingMenu'
import { intervalToDuration } from 'date-fns'
import { InAppBrowser } from 'react-native-inappbrowser-reborn'
import { AppText, typography } from '@/components/AppText'
import { colors } from '@/components/colors'
import { EnrichedMarkdownText } from 'react-native-enriched-markdown'
import { DEFAULT_DATA_POLICY, useConfigStore } from '@/services/configStore'

type RecordingDetailsRouteProp = RouteProp<
  RootStackParamList,
  'RecordingDetails'
>

type StackNavigationProp = NativeStackNavigationProp<RootStackParamList>

export default function RecordingDetailsScreen() {
  const route = useRoute<RecordingDetailsRouteProp>()
  const navigation = useNavigation<StackNavigationProp>()
  const { id } = route.params
  const { t } = useTranslation()
  const insets = useInsets()

  const originalFileKeptDays = useConfigStore(
    (state) =>
      state.config?.data_policy?.original_file_data_delete_after_days ??
      DEFAULT_DATA_POLICY.original_file_data_delete_after_days
  )

  const transcriptDataKeptFor = useConfigStore(
    (state) =>
      state.config?.data_policy?.file_auto_hard_delete_after_days ??
      DEFAULT_DATA_POLICY.file_auto_hard_delete_after_days
  )

  const [openMetaInfo, setOpenMetaInfo] = useState(false)
  useEffect(() => {
    if (openMetaInfo) {
      Alert.alert(
        t('recordings.dataPolicy.alertTitle'),
        t('recordings.dataPolicy.alertDescription', {
          originalDataKeptFor: originalFileKeptDays,
          transcriptDataKeptFor: transcriptDataKeptFor,
        }),
        [
          {
            text: t('recordings.dataPolicy.alertAction'),
            onPress: () => setOpenMetaInfo(false),
          },
        ]
      )
    }
  }, [openMetaInfo, originalFileKeptDays, t, transcriptDataKeptFor])

  const recordingQ = useGetFile(id)
  const recording = recordingQ.data

  const { lastAiJobTranscript } = useMemo(
    () => getMainAiJobs(recordingQ.data?.ai_jobs),
    [recordingQ.data?.ai_jobs]
  )

  const openInDocs = useOpenInDocsMutation()
  const handleOpenInDocs = useCallback(() => {
    if (lastAiJobTranscript?.id && lastAiJobTranscript.status === 'success') {
      openInDocs.mutate(lastAiJobTranscript, {
        onSuccess: async (res) => {
          const isAvailable = await InAppBrowser.isAvailable()
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
            })
          } else {
            await Linking.openURL(res.doc_url)
          }
        },
      })
    }
  }, [lastAiJobTranscript, openInDocs])

  const transcriptQ = useTranscript(lastAiJobTranscript)
  const transcriptSegments = useMemo(
    () => buildTranscriptViewSegments(transcriptQ.data),
    [transcriptQ.data]
  )

  const transcriptMarkdown = useMemo(() => {
    if (transcriptSegments.length === 0) {
      return null
    }
    let out = `# ${recording!.title}\n\n`
    transcriptSegments.forEach((segment) => {
      out += `**${formatTimestamp(segment.start ?? -1)} · ${t(
        'transcript.speaker'
      )} ${segment.speaker}** ${segment.text} \n\n`
    })
    return out
  }, [recording, transcriptSegments, t])

  const onDeleted = useCallback(() => {
    navigation.goBack()
  }, [navigation])

  const handleShareMarkdown = useCallback(async () => {
    if (transcriptMarkdown) {
      await Share.share({
        message: transcriptMarkdown,
      })
    }
  }, [transcriptMarkdown])

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
          <RecordingMenu recording={recording} onDeleted={onDeleted} />
        ) : (
          <View style={styles.iconButton} />
        )}
      </View>

      {recording && (
        <Pressable
          style={({ pressed }) => [
            styles.metaRow,
            pressed && { backgroundColor: colors.backgroundSubtlePressed },
          ]}
          onPress={() => setOpenMetaInfo(true)}
        >
          <View style={styles.metaElement}>
            <Lucide
              name="calendar-days"
              size={16}
              color={colors.neutralSecondary}
              style={styles.metaElementIcon}
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

          <View style={styles.metaElement}>
            <Lucide
              name="clock-3"
              size={16}
              color={colors.neutralSecondary}
              style={styles.metaElementIcon}
            />
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
            </AppText>
          </View>

          <View style={styles.metaElement}>
            <Lucide
              name="history"
              size={16}
              color={colors.warning}
              style={styles.metaElementIcon}
            />

            <AppText
              variant="mutedWarning"
              style={styles.warningDataPolicyText}
            >
              {recording.lifecycle_state === 'active'
                ? t('recordings.dataPolicy.audioKeptUntil', {
                    value: recording.original_file_file_delete_at,
                  })
                : t('recordings.dataPolicy.fileKeptUntil', {
                    value: recording.will_auto_delete_at,
                  })}
            </AppText>
          </View>
        </Pressable>
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
            <EnrichedMarkdownText
              selectable={true}
              markdownStyle={{
                strong: typography.bodyBold,
                paragraph: typography.body,
              }}
              markdown={transcriptSegments
                .map(
                  (segment) =>
                    `**${formatTimestamp(segment.start ?? -1)} · ${t('transcript.speaker')} ${segment.speaker}**  ${segment.text.trim()}`
                )
                .join('\n\n')}
            />
          )}
        </View>
      </ScrollView>

      {transcriptSegments.length > 0 && (
        <View
          style={[
            styles.bottomBarContainer,
            { bottom: 8 + insets.paddingBottom },
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
                {t('recordings.openInDocs')}
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
  )
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
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    rowGap: 8,
    columnGap: 16,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 6,
    marginBottom: 8,
    marginHorizontal: 8,
    flexWrap: 'wrap',
    backgroundColor: colors.backgroundNeutralTertiary,
    minHeight: 40,
  },
  metaElement: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
  },
  metaElementIcon: {
    marginBottom: -2,
  },
  popover: { borderRadius: 12, position: 'static' },
  transcriptContainer: {},
  warningDataPolicyText: {
    flexShrink: 1,
    textAlign: 'center',
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
    width: '100%',
    paddingHorizontal: 8,
    padding: 8,
    display: 'flex',
    borderRadius: 12,
    backgroundColor: colors.backgroundBase,
    borderWidth: 1,
    borderColor: colors.surfacePrimary,
    boxShadow: [
      {
        blurRadius: 12,
        spreadDistance: 4,
        color: colors.backgroundNeutralTertiary,
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
})
