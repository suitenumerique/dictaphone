import React, { useCallback, useRef } from 'react'
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native'
import Swipeable from 'react-native-gesture-handler/ReanimatedSwipeable'
import Animated, {
  interpolate,
  type SharedValue,
  useAnimatedStyle,
  useDerivedValue,
  useSharedValue,
} from 'react-native-reanimated'
import type { TFunction } from 'i18next'
import { Lucide } from '@react-native-vector-icons/lucide'
import { intervalToDuration } from 'date-fns'
import { trigger as triggerHaptic } from 'react-native-haptic-feedback'
import { runOnJS } from 'react-native-worklets'
import type {
  LocalOrRemoteRecording,
  RemoteRecording,
} from '@/screens/recordings/types'
import { getMainAiJobs } from '@/features/ai-jobs/utils/getMainAiJobs'
// @ts-expect-error Icon
import FileDisabledIcon from '@/assets/icons/file-disabled.svg'
// @ts-expect-error Icon
import FileIcon from '@/assets/icons/file.svg'
// @ts-expect-error Icon
import WarningIcon from '@/assets/icons/warning.svg'
// @ts-expect-error Icon
import PauseIcon from '@/assets/icons/pause.svg'
import UploadProgress from '@/components/UploadProgress'
import { AppText } from '@/components/AppText'
import { colors } from '@/components/colors'
import { useTranslation } from 'react-i18next'

const OPEN_STATE_THRESHOLD = 60
const RIGHT_ACTIONS_PANEL_WIDTH = 100
const PROGRESS_THRESHOLD = OPEN_STATE_THRESHOLD / RIGHT_ACTIONS_PANEL_WIDTH

export type SwipeableRowRef = React.ElementRef<typeof Swipeable>

type StatusIndicatorProps = {
  item: LocalOrRemoteRecording
  uploadBlockReason: UploadBlockReason
}

export type UploadBlockReason =
  | 'not-logged-in'
  | 'ok'
  | 'offline'
  | 'wifiOnly'
  | 'other'

function StatusIndicator({ item, uploadBlockReason }: StatusIndicatorProps) {
  if (item.kind === 'fake') {
    return <FileDisabledIcon />
  }
  if (item.kind === 'local') {
    if (uploadBlockReason === 'not-logged-in') {
      return <Lucide name="user-round-x" size={16} />
    }
    if (uploadBlockReason === 'wifiOnly') {
      return <Lucide name="wifi-off" size={16} color={colors.warning} />
    }
    if (uploadBlockReason === 'offline' || uploadBlockReason === 'other') {
      return <PauseIcon />
    }
    if (item.uploadingStatus === 'uploading') {
      return <ActivityIndicator size="small" />
    }
    return <WarningIcon />
  }

  const { lastAiJobTranscript } = getMainAiJobs(item.ai_jobs)
  if (lastAiJobTranscript?.status === 'failed') {
    return <WarningIcon />
  }
  if (lastAiJobTranscript?.status === 'success') {
    return <FileIcon />
  }
  return <ActivityIndicator size="small" />
}

function formatRecordMeta(
  recording: LocalOrRemoteRecording,
  t: TFunction,
  uploadBlockReason: UploadBlockReason
): string {
  if (recording.kind === 'fake') {
    return ''
  }

  const dateLabel = t('shared.utils.formatDateTime', {
    value: recording.created_at,
  })
  const durationLabel = t('shared.utils.duration', {
    duration: intervalToDuration({
      start: 0,
      end: recording.duration_seconds * 1000,
    }),
  })

  if (recording.kind === 'local') {
    if (uploadBlockReason === 'wifiOnly') {
      return `${durationLabel} • ${t('recordings.wifiOnlySync')}`
    }
    if (uploadBlockReason === 'offline' || uploadBlockReason === 'other') {
      return `${durationLabel} • ${t('recordings.meta.offline')}`
    }
    if (uploadBlockReason === 'not-logged-in') {
      return `${durationLabel} • ${t('recordings.meta.loginToSync')}`
    }
    if (recording.uploadingStatus === 'uploading') {
      return `${durationLabel} • ${t('recordings.meta.uploading')}`
    }
    if (
      recording.uploadingStatus === 'failed' ||
      recording.uploadingStatus === 'to_upload'
    ) {
      return `${durationLabel} • ${t('recordings.meta.waitingForUpload')}`
    }
    return `${durationLabel} • ${dateLabel}`
  }

  const { lastAiJobTranscript } = getMainAiJobs(recording.ai_jobs)
  if (lastAiJobTranscript?.status === 'failed') {
    return `${durationLabel} • ${dateLabel} • ${t('recordings.meta.processingFailed')}`
  }
  if (lastAiJobTranscript?.status === 'success') {
    return `${durationLabel} • ${dateLabel}`
  }
  return `${durationLabel} • ${dateLabel} • ${t('recordings.meta.processing')}`
}

function DeleteRightAction({
  progress,
  onPress,
}: {
  progress: SharedValue<number>
  onPress: () => void
}) {
  const { t } = useTranslation()
  const didFireHaptic = useSharedValue(false)

  const handleValueChanged = useCallback((value: number) => {
    if (value > PROGRESS_THRESHOLD) {
      triggerHaptic('impactMedium', {
        enableVibrateFallback: true,
        ignoreAndroidSystemSettings: true,
      })
    }
    if (value < PROGRESS_THRESHOLD) {
      triggerHaptic('impactLight', {
        enableVibrateFallback: true,
        ignoreAndroidSystemSettings: true,
      })
    }
  }, [])

  useDerivedValue(() => {
    const isAboveThreshold = progress.value > PROGRESS_THRESHOLD
    if (isAboveThreshold !== didFireHaptic.value) {
      didFireHaptic.value = isAboveThreshold
      runOnJS(handleValueChanged)(progress.value)
    }
  })

  const animatedButtonStyle = useAnimatedStyle(() => ({
    transform: [
      {
        translateX: interpolate(
          progress.value,
          [0, 1],
          [1.5 * OPEN_STATE_THRESHOLD, 0]
        ),
      },
    ],
    opacity: interpolate(progress.value, [0, 0.1], [0, 1]),
  }))

  return (
    <Animated.View style={[styles.rightActionContainer, animatedButtonStyle]}>
      <Pressable
        onPress={onPress}
        style={({ pressed }) => [
          styles.deleteAction,
          pressed && styles.deleteActionPressed,
        ]}
        accessibilityLabel={t('recordings.delete')}
        accessibilityRole="button"
      >
        <Lucide name="trash-2" size={20} color={colors.errorSecondary} />
      </Pressable>
    </Animated.View>
  )
}

function SwipeableRemoteRow({
  item,
  onDelete,
  onWillOpen,
  onClose,
  children,
}: {
  item: RemoteRecording
  onDelete: (fileId: string) => void
  onWillOpen: (row: SwipeableRowRef) => void
  onClose: (row: SwipeableRowRef) => void
  children: React.ReactNode
}) {
  const swipeableRef = useRef<SwipeableRowRef | null>(null)

  const handleDeletePress = useCallback(() => {
    if (!swipeableRef.current) {
      return
    }
    swipeableRef.current.close()
    onDelete(item.id)
  }, [item.id, onDelete])

  const handleSwipeableWillOpen = useCallback(() => {
    if (swipeableRef.current) {
      onWillOpen(swipeableRef.current)
    }
  }, [onWillOpen])

  const handleSwipeableClose = useCallback(() => {
    if (swipeableRef.current) {
      onClose(swipeableRef.current)
    }
  }, [onClose])

  const renderRightActions = useCallback(
    (progress: SharedValue<number>) => (
      <DeleteRightAction progress={progress} onPress={handleDeletePress} />
    ),
    [handleDeletePress]
  )

  return (
    <Swipeable
      ref={swipeableRef}
      friction={1.5}
      overshootRight={false}
      rightThreshold={OPEN_STATE_THRESHOLD}
      enableTrackpadTwoFingerGesture
      onSwipeableWillOpen={handleSwipeableWillOpen}
      onSwipeableClose={handleSwipeableClose}
      renderRightActions={renderRightActions}
    >
      {children}
    </Swipeable>
  )
}

type RecordingListItemProps = {
  item: LocalOrRemoteRecording
  uploadBlockReason: UploadBlockReason
  t: TFunction
  onOpen: (item: LocalOrRemoteRecording) => void
  onDelete: (fileId: string) => void
  onWillOpenRow: (row: SwipeableRowRef) => void
  onCloseRow: (row: SwipeableRowRef) => void
}

export function RecordingListItem({
  item,
  uploadBlockReason,
  t,
  onOpen,
  onDelete,
  onWillOpenRow,
  onCloseRow,
}: RecordingListItemProps) {
  const isOpenableRemoteRecording =
    item.kind === 'remote' &&
    getMainAiJobs(item.ai_jobs).lastAiJobTranscript?.status === 'success'

  const card = (
    <Pressable
      style={({ pressed }) => [
        styles.itemCard,
        pressed && item.kind === 'remote' && styles.itemCardPressed,
      ]}
      disabled={!isOpenableRemoteRecording}
      onPress={() => onOpen(item)}
    >
      <View style={styles.itemHeader}>
        <View style={styles.cardHeaderLeft}>
          <StatusIndicator item={item} uploadBlockReason={uploadBlockReason} />
        </View>
        <View style={styles.cardHeaderRight}>
          {item.kind !== 'fake' ? (
            <>
              <AppText
                variant="bodyMedium"
                size="lg"
                color={
                  item.kind !== 'remote'
                    ? colors.neutralSecondary
                    : colors.textPrimary
                }
                numberOfLines={1}
              >
                {item.title}
              </AppText>
              <AppText variant="muted" size="md" numberOfLines={1}>
                {formatRecordMeta(item, t, uploadBlockReason)}
              </AppText>
              {item.kind === 'local' &&
                item.uploadingStatus === 'uploading' && (
                  <UploadProgress
                    uploadedBytes={item.uploadProgress?.uploadedBytes ?? 0}
                    totalBytes={item.uploadProgress?.totalBytes ?? 0}
                  />
                )}
            </>
          ) : (
            <>
              <View style={styles.recordingTitleSkeleton} />
              <View style={styles.metaSkeleton} />
            </>
          )}
        </View>
      </View>
    </Pressable>
  )

  if (item.kind !== 'remote') {
    return card
  }

  return (
    <SwipeableRemoteRow
      item={item}
      onDelete={onDelete}
      onWillOpen={onWillOpenRow}
      onClose={onCloseRow}
    >
      {card}
    </SwipeableRemoteRow>
  )
}

const styles = StyleSheet.create({
  itemCard: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
  },
  itemCardPressed: {
    backgroundColor: colors.backgroundSubtlePressed,
  },
  itemHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-start',
    gap: 4,
  },
  cardHeaderLeft: {
    width: 50,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  cardHeaderRight: {
    flex: 1,
    gap: 2,
  },
  recordingTitleSkeleton: {
    width: 140,
    height: 14,
    borderRadius: 6,
    backgroundColor: colors.backgroundNeutralTertiary,
  },
  metaSkeleton: {
    width: 100,
    height: 12,
    borderRadius: 6,
    backgroundColor: colors.backgroundNeutralTertiary,
  },
  rightActionContainer: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 16,
  },
  deleteAction: {
    width: RIGHT_ACTIONS_PANEL_WIDTH,
    paddingHorizontal: 4,
    marginVertical: 2,
    borderRadius: 8,
    alignItems: 'center',
    height: 40,
    justifyContent: 'center',
    flexDirection: 'row',
    overflow: 'hidden',
    backgroundColor: colors.backgroundErrorSecondary,
  },
  deleteActionPressed: {
    backgroundColor: colors.backgroundErrorSecondaryPressed,
  },
})
