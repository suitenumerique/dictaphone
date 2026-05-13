import React, { useCallback, useMemo, useRef, useState } from 'react'
import {
  ActivityIndicator,
  Alert,
  FlatList,
  StyleSheet,
  View,
} from 'react-native'
import { useTranslation } from 'react-i18next'
import { useNetInfo } from '@react-native-community/netinfo'
import { useNavigation } from '@react-navigation/core'
import type { NativeStackNavigationProp } from '@react-navigation/native-stack'
import { useQueryClient } from '@tanstack/react-query'
import { keys } from '@/api/queryKeys'
import { MOCK_DATA } from '@/api/constants'
import { mockedFiles } from '@/features/files/api/mockData'
import { useLocalRecordings } from '@/features/recordings/hooks/useLocalRecordings'
import {
  setBypassWifiOnly,
  useSettingsStore,
  useUploadStore,
} from '@/services/storage'
import { useUser } from '@/features/auth/api/useUser'
import { useListMyFilesInfinite } from '@/features/files/api/listFiles'
import { useDeleteFile } from '@/features/files/api/deleteFile'
import type { RootStackParamList } from '@/navigation/types'
import { useInsets } from '@/utils/useInsets'
import { AppText } from '@/components/AppText'
import { colors } from '@/components/colors'
import type { LocalOrRemoteRecording } from '@/screens/recordings/types'
import { RecordingsTopBar } from '@/screens/recordings/components/RecordingsTopBar'
import {
  RecordingListItem,
  type SwipeableRowRef,
  type UploadBlockReason,
} from '@/screens/recordings/components/RecordingListItem'
import { StartRecordingSection } from '@/screens/recordings/components/StartRecordingSection'

export default function RecordingsScreen() {
  const { t } = useTranslation()
  const netInfo = useNetInfo()
  const navigation =
    useNavigation<NativeStackNavigationProp<RootStackParamList>>()
  const insets = useInsets()
  const { recordings, updateRecording } = useLocalRecordings()
  const { isLoggedIn, isLoading } = useUser()
  const { settings } = useSettingsStore()
  const queryClient = useQueryClient()
  const deleteMutation = useDeleteFile()

  const filesQ = useListMyFilesInfinite({
    pageSize: 20,
    filters: {
      type: 'audio_recording',
      is_creator_me: true,
      is_deleted: false,
      upload_state: 'ready',
    },
  })

  const isOnline =
    netInfo.isConnected === true && netInfo.isInternetReachable !== false
  const isOnWifi = netInfo.type === 'wifi'
  const hasPendingUploads = recordings.some(
    (recording) =>
      recording.uploadingStatus === 'to_upload' ||
      recording.uploadingStatus === 'uploading'
  )

  const wifiBypassActivated = useUploadStore((state) => state.bypassWifiOnly)
  const [fileIdBeingDeleted, setFileIdBeingDeleted] = useState<string | null>(
    null
  )
  const openedSwipeableRef = useRef<SwipeableRowRef | null>(null)

  const uploadBlockReason: UploadBlockReason = !isLoggedIn
    ? 'not-logged-in'
    : !isOnline
      ? 'offline'
      : settings.wifiOnlyUpload && !isOnWifi && !wifiBypassActivated
        ? 'wifiOnly'
        : 'ok'
  const showWifiOnlyCard =
    isLoggedIn &&
    isOnline &&
    !isOnWifi &&
    settings.wifiOnlyUpload &&
    hasPendingUploads &&
    !wifiBypassActivated

  const allRecordings = useMemo<LocalOrRemoteRecording[]>(() => {
    const out: LocalOrRemoteRecording[] = recordings.map((recording) => ({
      ...recording,
      kind: 'local',
    }))

    if (MOCK_DATA) {
      mockedFiles.forEach((file) => {
        out.push({ ...file, kind: 'remote' })
      })
      return out
    }

    if (isOnline) {
      for (const page of filesQ.data?.pages ?? []) {
        for (const recording of page.results) {
          if (recording.id !== fileIdBeingDeleted) {
            out.push({ ...recording, kind: 'remote' })
          }
        }
      }
    } else {
      for (let i = 0; i < 5; i++) {
        out.push({ id: `fake-${i}`, kind: 'fake' })
      }
    }

    return out
  }, [filesQ.data?.pages, fileIdBeingDeleted, isOnline, recordings])

  const handleRefresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: [keys.files] })

    for (const recording of recordings) {
      if (recording.uploadingStatus === 'failed') {
        updateRecording(recording.id, { uploadingStatus: 'to_upload' })
      }
    }
  }, [queryClient, recordings, updateRecording])

  const handleSyncNow = useCallback(() => {
    setBypassWifiOnly(true)
  }, [])

  const handleStartRecording = useCallback(() => {
    navigation.navigate('RecordingInProgress')
  }, [navigation])

  const handleOpenRecording = useCallback(
    (item: LocalOrRemoteRecording) => {
      if (openedSwipeableRef.current) {
        openedSwipeableRef.current.close()
        openedSwipeableRef.current = null
      }
      if (item.kind === 'fake') {
        return
      }
      navigation.navigate('RecordingDetails', { id: item.id })
    },
    [navigation]
  )

  const executeDeleteRecording = useCallback(
    async (fileId: string) => {
      try {
        setFileIdBeingDeleted(fileId)
        await deleteMutation.mutateAsync({ fileId })
      } catch {
        Alert.alert(
          t('recordings.menu.errorTitle'),
          t('recordings.menu.deleteError')
        )
      } finally {
        setFileIdBeingDeleted(null)
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

  const renderItem = useCallback(
    ({ item }: { item: LocalOrRemoteRecording }) => (
      <RecordingListItem
        item={item}
        uploadBlockReason={uploadBlockReason}
        t={t}
        onOpen={handleOpenRecording}
        onDelete={handleDeleteRecording}
        onWillOpenRow={handleRowWillOpen}
        onCloseRow={handleRowClose}
      />
    ),
    [
      uploadBlockReason,
      handleDeleteRecording,
      handleOpenRecording,
      handleRowClose,
      handleRowWillOpen,
      t,
    ]
  )

  return (
    <View style={[styles.container, insets]}>
      <RecordingsTopBar
        isOnline={isOnline}
        isLoading={isLoading}
        isLoggedIn={isLoggedIn}
        showWifiOnlyCard={showWifiOnlyCard}
        onSyncNow={handleSyncNow}
        t={t}
      />

      {isOnline && (isLoggedIn || isLoading) && filesQ.isPending && (
        <ActivityIndicator size="large" />
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

      <StartRecordingSection onStartRecording={handleStartRecording} t={t} />
    </View>
  )
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
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
})
