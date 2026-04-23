import React, { useCallback, useMemo, useRef, useState } from 'react'
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Pressable,
  StyleSheet,
  View,
} from 'react-native'
import Swipeable from 'react-native-gesture-handler/ReanimatedSwipeable'
import Animated, {
  interpolate,
  SharedValue,
  useAnimatedStyle,
  useDerivedValue,
} from 'react-native-reanimated'
import { useTranslation } from 'react-i18next'
import type { LocalRecording } from '@/types/localRecording'
import { useLocalRecordings } from '@/features/recordings/hooks/useLocalRecordings'
import { Lucide } from '@react-native-vector-icons/lucide'
import { useNetInfo } from '@react-native-community/netinfo'
import { useNavigation } from '@react-navigation/core' // @ts-expect-error Icon
import LogoWithName from '../assets/logo-with-name.svg' // @ts-expect-error Icon
import RecordIcon from '@/assets/icons/record.svg' // @ts-expect-error Icon
import FileDisabledIcon from '@/assets/icons/file-disabled.svg' // @ts-expect-error Icon
import FileIcon from '@/assets/icons/file.svg' // @ts-expect-error Icon
import WarningIcon from '@/assets/icons/warning.svg' // @ts-expect-error Icon
import PauseIcon from '@/assets/icons/pause.svg'
import { useUser } from '@/features/auth/api/useUser'
import { LoginButton } from '@/components/LoginButton'
import { useListMyFilesInfinite } from '@/features/files/api/listFiles'
import type { ApiFileItem } from '@/features/files/api/types'
import type { NativeStackNavigationProp } from '@react-navigation/native-stack'
import type { RootStackParamList } from '@/navigation/types'
import { useQueryClient } from '@tanstack/react-query'
import { keys } from '@/api/queryKeys'
import { getMainAiJobs } from '@/features/ai-jobs/utils/getMainAiJobs'
import { intervalToDuration } from 'date-fns'
import MainMenu from '@/components/MainMenu'
import { useInsets } from '@/utils/useInsets'
import { AppText } from '@/components/AppText'
import { colors } from '@/components/colors'
import { useDeleteFile } from '@/features/files/api/deleteFile'
import { trigger as triggerHaptic } from 'react-native-haptic-feedback'
import { runOnJS } from 'react-native-worklets'

type LocalOrRemoteRecording =
  | (ApiFileItem & { kind: 'remote' })
  | (LocalRecording & { kind: 'local' })
  | { kind: 'fake'; id: string }

type RemoteRecording = ApiFileItem & { kind: 'remote' }

function StatusIndicator({
  item,
  canUpload,
}: {
  item: LocalOrRemoteRecording
  canUpload: boolean
}) {
  if (item.kind === 'fake') {
    return <FileDisabledIcon />
  }
  if (item.kind === 'local') {
    if (!canUpload) {
      return <PauseIcon />
    }
    if (item.uploadingStatus === 'uploading') {
      return <ActivityIndicator size="small" />
    } else {
      return <WarningIcon />
    }
  }

  if (item.kind === 'remote') {
    const { lastAiJobTranscript } = getMainAiJobs(item.ai_jobs)
    if (lastAiJobTranscript?.status === 'failed') {
      return <WarningIcon />
    } else if (lastAiJobTranscript?.status === 'success') {
      return <FileIcon />
    } else {
      return <ActivityIndicator size="small" />
    }
  }

  return <FileIcon />
}

function formatRecordMeta(
  recording: LocalOrRemoteRecording,
  t: ReturnType<typeof useTranslation>['t'],
  isOnline: boolean,
  isLoggedIn: boolean
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
    if (!isLoggedIn) {
      return `${durationLabel} • ${t('recordings.meta.loginToSync')}`
    } else if (!isOnline) {
      return `${durationLabel} • ${t('recordings.meta.offline')}`
    } else if (recording.uploadingStatus === 'uploading') {
      return `${durationLabel} • ${t('recordings.meta.uploading')}`
    } else if (recording.uploadingStatus === 'failed') {
      return `${durationLabel} • ${t('recordings.meta.waitingForUpload')}`
    } else if (recording.uploadingStatus === 'to_upload') {
      return `${durationLabel} • ${t('recordings.meta.waitingForUpload')}`
    }
    return `${durationLabel} • ${dateLabel}`
  }

  if (recording.kind === 'remote') {
    const { lastAiJobTranscript } = getMainAiJobs(recording.ai_jobs)
    if (lastAiJobTranscript?.status === 'failed') {
      return `${durationLabel} • ${dateLabel} • ${t(
        'recordings.meta.processingFailed'
      )}`
    } else if (lastAiJobTranscript?.status === 'success') {
      return `${durationLabel} • ${dateLabel}`
    } else {
      return `${durationLabel} • ${dateLabel} • ${t(
        'recordings.meta.processing'
      )}`
    }
  }

  return ''
}

const OPEN_STATE_THRESHOLD = 60
const RIGHT_ACTIONS_PANEL_WIDTH = 100
const PROGRESS_THRESHOLD = OPEN_STATE_THRESHOLD / RIGHT_ACTIONS_PANEL_WIDTH

type SwipeableRowRef = React.ElementRef<typeof Swipeable>

function DeleteRightAction({
  progress,
  onPress,
}: {
  progress: SharedValue<number>
  onPress: () => void
}) {
  const didFireHapticRef = useRef(false)

  const handleValueChanged = useCallback((value: number) => {
    if (value > PROGRESS_THRESHOLD && !didFireHapticRef.current) {
      didFireHapticRef.current = true
      triggerHaptic('impactMedium', {
        enableVibrateFallback: true,
        ignoreAndroidSystemSettings: true,
      })
    }
    if (value < PROGRESS_THRESHOLD && didFireHapticRef.current) {
      triggerHaptic('impactLight', {
        enableVibrateFallback: true,
        ignoreAndroidSystemSettings: true,
      })
      didFireHapticRef.current = false
    }
  }, [])

  useDerivedValue(() => {
    runOnJS(handleValueChanged)(progress.value)
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
    if (!swipeableRef.current) {
      return
    }
    onWillOpen(swipeableRef.current)
  }, [onWillOpen])

  const handleSwipeableClose = useCallback(() => {
    if (!swipeableRef.current) {
      return
    }
    onClose(swipeableRef.current)
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

export default function RecordingsScreen() {
  const { t } = useTranslation()
  const netInfo = useNetInfo()
  const navigation =
    useNavigation<NativeStackNavigationProp<RootStackParamList>>()
  const insets = useInsets()
  const { recordings, updateRecording } = useLocalRecordings()
  const { isLoggedIn, isLoading } = useUser()
  const filesQ = useListMyFilesInfinite({
    pageSize: 20,
    filters: {
      type: 'audio_recording',
      is_creator_me: true,
      is_deleted: false,
      upload_state: 'ready',
    },
  })
  const queryClient = useQueryClient()
  const handleRefresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: [keys.files] })

    // We try to reupload failed upload recordings
    for (const recording of recordings) {
      if (recording.uploadingStatus === 'failed') {
        updateRecording(recording.id, {
          uploadingStatus: 'to_upload',
        })
      }
    }
  }, [recordings, queryClient, updateRecording])

  const deleteMutation = useDeleteFile()

  const isOnline =
    netInfo.isConnected === true && netInfo.isInternetReachable !== false
  const [fileIdBeingDeleted, setfileIdBeingDeleted] = useState<string | null>(
    null
  )
  const openedSwipeableRef = useRef<SwipeableRowRef | null>(null)

  const allRecordings = useMemo<LocalOrRemoteRecording[]>(() => {
    const out: LocalOrRemoteRecording[] = []
    for (const recording of recordings) {
      out.push({
        ...recording,
        kind: 'local',
      })
    }
    if (isOnline) {
      for (const page of filesQ.data?.pages ?? []) {
        for (const recording of page.results) {
          if (recording.id !== fileIdBeingDeleted) {
            out.push({
              ...recording,
              kind: 'remote',
            })
          }
        }
      }
    } else {
      for (let i = 0; i < 5; i++) {
        out.push({
          id: `fake-${i}`,
          kind: 'fake',
        })
      }
    }
    return out
  }, [isOnline, recordings, filesQ.data?.pages, fileIdBeingDeleted])

  const handleStartRecording = useCallback(() => {
    navigation.navigate('RecordingInProgress')
  }, [navigation])

  const handleOpenRecording = useCallback(
    (item: LocalOrRemoteRecording) => {
      if (item.kind === 'fake') {
        return
      }
      navigation.navigate('RecordingDetails', {
        id: item.id,
      })
    },
    [navigation]
  )

  const executeDeleteRecording = useCallback(
    async (fileId: string) => {
      try {
        setfileIdBeingDeleted(fileId)
        await deleteMutation.mutateAsync({ fileId })
      } catch {
        Alert.alert(
          t('recordings.menu.errorTitle'),
          t('recordings.menu.deleteError')
        )
      } finally {
        setfileIdBeingDeleted(null)
      }
    },
    [deleteMutation, t]
  )

  const handleDeleteRecording = useCallback(
    (fileId: string) => {
      void executeDeleteRecording(fileId)
    },
    [executeDeleteRecording]
  )

  const handleRowWillOpen = useCallback((row: SwipeableRowRef) => {
    if (openedSwipeableRef.current && openedSwipeableRef.current !== row) {
      openedSwipeableRef.current.close()
    }
    openedSwipeableRef.current = row
  }, [])

  const handleRowClose = useCallback((row: SwipeableRowRef) => {
    if (openedSwipeableRef.current === row) {
      openedSwipeableRef.current = null
    }
  }, [])

  const handleOpenRecordingWithSwipeClose = useCallback(
    (item: LocalOrRemoteRecording) => {
      if (openedSwipeableRef.current) {
        openedSwipeableRef.current.close()
        openedSwipeableRef.current = null
      }
      handleOpenRecording(item)
    },
    [handleOpenRecording]
  )

  const renderItemCard = useCallback(
    (item: LocalOrRemoteRecording) => (
      <Pressable
        style={({ pressed }) => [
          styles.itemCard,
          pressed && item.kind === 'remote' && styles.itemCardPressed,
        ]}
        disabled={
          item.kind !== 'remote' ||
          getMainAiJobs(item.ai_jobs).lastAiJobTranscript?.status !== 'success'
        }
        onPress={() => handleOpenRecordingWithSwipeClose(item)}
      >
        <View style={styles.itemHeader}>
          <View style={styles.cardHeaderLeft}>
            <StatusIndicator item={item} canUpload={isOnline} />
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
                  {formatRecordMeta(item, t, isOnline, isLoggedIn)}
                </AppText>
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
    ),
    [handleOpenRecordingWithSwipeClose, isLoggedIn, isOnline, t]
  )

  const renderItem = useCallback(
    ({ item }: { item: LocalOrRemoteRecording }) => {
      const card = renderItemCard(item)

      if (item.kind !== 'remote') {
        return card
      }

      return (
        <SwipeableRemoteRow
          item={item}
          onDelete={handleDeleteRecording}
          onWillOpen={handleRowWillOpen}
          onClose={handleRowClose}
        >
          {card}
        </SwipeableRemoteRow>
      )
    },
    [handleDeleteRecording, handleRowClose, handleRowWillOpen, renderItemCard]
  )

  return (
    <View style={[styles.container, insets]}>
      <View style={styles.topBar}>
        <View style={styles.topBarHeader}>
          <LogoWithName style={styles.title} />
          <MainMenu />
        </View>
        {isOnline && !isLoading && !isLoggedIn && (
          <View style={styles.loginCard}>
            <AppText
              variant="body"
              align="center"
              color={colors.neutralTertiary}
            >
              {t('recordings.loginHelper')}
            </AppText>
            <LoginButton />
          </View>
        )}
        {!isOnline && (
          <View style={[styles.networkCard, styles.offlineCard]}>
            <Lucide name={'wifi-off'} size={16} color={colors.warning} />
            <AppText variant="body" color={colors.warning}>
              {t('recordings.offline')}
            </AppText>
          </View>
        )}
      </View>

      {isOnline && (isLoggedIn || isLoading) && filesQ.isPending && (
        <ActivityIndicator size={'large'} />
      )}

      <FlatList
        data={allRecordings}
        keyExtractor={(item) => item.id}
        contentContainerStyle={[
          styles.listContent,
          {
            marginBottom: insets.paddingBottom + 40,
          },
          { paddingBottom: 13 },
        ]}
        renderItem={renderItem}
        ItemSeparatorComponent={<View style={styles.recordingListSeparator} />}
        onEndReached={() => {
          if (isOnline && filesQ.hasNextPage && !filesQ.isFetchingNextPage) {
            filesQ.fetchNextPage()
          }
        }}
        refreshing={
          isOnline && (isLoggedIn || allRecordings.length > 0)
            ? filesQ.isRefetching
            : undefined
        }
        onRefresh={
          isOnline && (isLoggedIn || allRecordings.length > 0)
            ? handleRefresh
            : undefined
        }
        ListFooterComponent={
          isOnline && !filesQ.isPending && allRecordings.length > 0 ? (
            filesQ.hasNextPage ? (
              <ActivityIndicator />
            ) : (
              <AppText
                variant="muted"
                size="sm"
                align="center"
                style={styles.listFooter}
              >
                {t('recordings.listFooter')}
              </AppText>
            )
          ) : undefined
        }
      />

      <View style={styles.startRecordingContainer}>
        <Pressable
          style={({ pressed }) => [
            styles.startRecordingButton,
            pressed && styles.startRecordingButtonPressed,
          ]}
          onPress={handleStartRecording}
        >
          <RecordIcon width={24} height={24} />
          <AppText variant="button" color={colors.errorSecondary}>
            {t('home.newRecording')}
          </AppText>
        </Pressable>

        <View style={styles.consentRow}>
          <AppText
            variant="muted"
            size="md"
            align="center"
            color={colors.neutralTertiary}
            style={styles.consentText}
          >
            <Lucide
              name="triangle-alert"
              color={colors.neutralTertiary}
              size={12}
            />{' '}
            {t('home.consentNotice')}
          </AppText>
        </View>
      </View>
    </View>
  )
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  topBar: {
    paddingHorizontal: 16,
    paddingTop: 4,
    paddingBottom: 10,
    gap: 12,
  },
  topBarHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingRight: 8,
  },
  loginCard: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 8,
    padding: 12,
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
  title: {
    marginBottom: 2,
  },
  networkCard: {
    borderRadius: 10,
    paddingVertical: 12,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: 1,
  },
  offlineCard: {
    backgroundColor: colors.warningSurface,
    borderColor: colors.warningBorder,
  },
  listContent: {},
  recordingListSeparator: {
    height: 1,
    backgroundColor: colors.surfacePrimary,
    marginVertical: 4,
    marginHorizontal: 12,
  },
  listFooter: {
    paddingTop: 36,
    paddingBottom: 22,
  },
  itemCard: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
  },
  itemCardPressed: {
    backgroundColor: colors.backgroundSubtlePressed,
  },
  rightActionContainer: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
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
  startRecordingContainer: {
    width: '100%',
    marginBottom: 8,
    padding: 8,
    gap: 8,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
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
  startRecordingButton: {
    backgroundColor: colors.backgroundErrorSecondary,
    borderRadius: 4,
    minHeight: 40,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 10,
    width: '100%',
  },
  startRecordingButtonPressed: {
    backgroundColor: colors.backgroundErrorSecondaryPressed,
  },
  consentRow: {},
  consentText: {
    flexShrink: 1,
  },
})
