import React, { useCallback, useMemo } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useTranslation } from 'react-i18next';
import type { LocalRecording } from '@/types/localRecording';
import { useLocalRecordings } from '@/features/recordings/hooks/useLocalRecordings';
import { Lucide } from '@react-native-vector-icons/lucide';
import { useNetInfo } from '@react-native-community/netinfo';
import { useNavigation } from '@react-navigation/core'; // @ts-expect-error
import LogoWithName from '../assets/logo-with-name.svg'; // @ts-expect-error
import RecordIcon from '@/assets/icons/record.svg'; // @ts-expect-error
import FileDisabledIcon from '@/assets/icons/file-disabled.svg'; // @ts-expect-error
import FileIcon from '@/assets/icons/file.svg'; // @ts-expect-error
import WarningIcon from '@/assets/icons/warning.svg'; // @ts-expect-error
import PauseIcon from '@/assets/icons/pause.svg';
import { useUser } from '@/features/auth/api/useUser';
import { LoginButton } from '@/features/auth/LoginButton';
import { useListMyFilesInfinite } from '@/features/files/api/listFiles';
import { ApiFileItem } from '@/features/files/api/types';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '@/navigation/types';
import { useQueryClient } from '@tanstack/react-query';
import { keys } from '@/api/queryKeys';
import { getMainAiJobs } from '@/features/ai-jobs/utils/getMainAiJobs';
import { intervalToDuration } from 'date-fns';
import MainMenu from '@/components/MainMenu';
import { useInsets } from '@/utils/useInsets';

type LocalOrRemoteRecording =
  | (ApiFileItem & { kind: 'remote' })
  | (LocalRecording & { kind: 'local' })
  | { kind: 'fake'; id: string };

function StatusIndicator({
  item,
  canUpload,
}: {
  item: LocalOrRemoteRecording;
  canUpload: boolean;
}) {
  if (item.kind === 'fake') {
    return <FileDisabledIcon />;
  }
  if (item.kind === 'local') {
    if (!canUpload) {
      return <PauseIcon />;
    }
    if (item.uploadingStatus === 'uploading') {
      return <ActivityIndicator size="small" />;
    } else {
      return <WarningIcon />;
    }
  }

  if (item.kind === 'remote') {
    const { lastAiJobTranscript } = getMainAiJobs(item.ai_jobs);
    if (lastAiJobTranscript?.status === 'failed') {
      return <WarningIcon />;
    } else if (lastAiJobTranscript?.status === 'success') {
      return <FileIcon />;
    } else {
      return <ActivityIndicator size="small" />;
    }
  }

  return <FileIcon />;
}

function formatRecordMeta(
  recording: LocalOrRemoteRecording,
  t: ReturnType<typeof useTranslation>['t'],
  isOnline: boolean,
  isLoggedIn: boolean,
): string {
  if (recording.kind === 'fake') {
    return '';
  }

  const dateLabel = t('shared.utils.formatDateTime', {
    value: recording.created_at,
  });
  const durationLabel = t('shared.utils.duration', {
    duration: intervalToDuration({
      start: 0,
      end: recording.duration_seconds * 1000,
    }),
  });

  if (recording.kind === 'local') {
    if (!isLoggedIn) {
      return `${durationLabel} • ${t('recordings.meta.loginToSync')}`;
    } else if (!isOnline) {
      return `${durationLabel} • ${t('recordings.meta.offline')}`;
    } else if (recording.uploadingStatus === 'uploading') {
      return `${durationLabel} • ${t('recordings.meta.uploading')}`;
    } else if (recording.uploadingStatus === 'failed') {
      return `${durationLabel} • ${t('recordings.meta.waitingForUpload')}`;
    } else if (recording.uploadingStatus === 'to_upload') {
      return `${durationLabel} • ${t('recordings.meta.waitingForUpload')}`;
    }
    {
      return `${durationLabel} • ${dateLabel}`;
    }
  }

  if (recording.kind === 'remote') {
    const { lastAiJobTranscript } = getMainAiJobs(recording.ai_jobs);
    if (lastAiJobTranscript?.status === 'failed') {
      return `${durationLabel} • ${dateLabel} • ${t(
        'recordings.meta.processingFailed',
      )}`;
    } else if (lastAiJobTranscript?.status === 'success') {
      return `${durationLabel} • ${dateLabel}`;
    } else {
      return `${durationLabel} • ${dateLabel} • ${t(
        'recordings.meta.processing',
      )}`;
    }
  }

  return '';
}

export default function RecordingsScreen() {
  const { t } = useTranslation();
  const netInfo = useNetInfo();
  const navigation =
    useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const insets = useInsets();
  const { recordings, isUploading } = useLocalRecordings();
  const { isLoggedIn, isLoading } = useUser();
  const filesQ = useListMyFilesInfinite({
    pageSize: 20,
    filters: {
      type: 'audio_recording',
      is_creator_me: true,
      is_deleted: false,
      upload_state: 'ready',
    },
  });
  const queryClient = useQueryClient();
  const isOnline =
    netInfo.isConnected === true && netInfo.isInternetReachable !== false;

  const allRecordings = useMemo<LocalOrRemoteRecording[]>(() => {
    const out: LocalOrRemoteRecording[] = [];
    for (const recording of recordings) {
      out.push({
        ...recording,
        kind: 'local',
      });
    }
    if (isOnline) {
      for (const page of filesQ.data?.pages ?? []) {
        for (const recording of page.results) {
          out.push({
            ...recording,
            kind: 'remote',
          });
        }
      }
    } else {
      for (let i = 0; i < 5; i++) {
        out.push({
          id: `fake-${i}`,
          kind: 'fake',
        });
      }
    }
    return out;
  }, [filesQ.data?.pages, recordings, isOnline]);

  const handleStartRecording = useCallback(() => {
    navigation.navigate('RecordingInProgress');
  }, [navigation]);

  const handleOpenRecording = useCallback(
    (item: LocalOrRemoteRecording) => {
      if (item.kind === 'fake') {
        return;
      }
      navigation.navigate('RecordingDetails', {
        id: item.id,
      });
    },
    [navigation],
  );

  const renderItem = ({ item }: { item: LocalOrRemoteRecording }) => {
    return (
      <Pressable
        style={({ pressed }) => [
          styles.itemCard,
          pressed && item.kind === 'remote' && styles.itemCardPressed,
        ]}
        disabled={item.kind !== 'remote'}
        onPress={() => handleOpenRecording(item)}
      >
        <View style={styles.itemHeader}>
          <View style={styles.cardHeaderLeft}>
            <StatusIndicator item={item} canUpload={isOnline} />
          </View>
          <View style={styles.cardHeaderRight}>
            {item.kind !== 'fake' ? (
              <>
                <Text
                  style={[
                    styles.recordingTitle,
                    item.kind !== 'remote' && styles.notAvailable,
                  ]}
                >
                  {item.title}
                </Text>
                <Text style={styles.meta}>
                  {formatRecordMeta(item, t, isOnline, isLoggedIn)}
                </Text>
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
    );
  };

  return (
    <View
      style={[
        styles.container,
        insets,
      ]}
    >
      <View style={styles.topBar}>
        <View style={styles.topBarHeader}>
          <LogoWithName style={styles.title} />
          <MainMenu />
        </View>
        {isOnline && !isLoading && !isLoggedIn && (
          <View style={styles.loginCard}>
            <Text style={styles.loginHelperText}>
              {t('recordings.loginHelper')}
            </Text>
            <LoginButton />
          </View>
        )}
        {!isOnline && (
          <View style={[styles.networkCard, styles.offlineCard]}>
            <Lucide
              name={'wifi-off'}
              size={16}
              color={styles.offlineText.color}
            />
            <Text style={[styles.networkText, styles.offlineText]}>
              {t('recordings.offline')}
            </Text>
          </View>
        )}
        {isUploading ? (
          <View style={styles.uploadingRow}>
            <ActivityIndicator size="small" color="#1D4ED8" />
            <Text style={styles.uploadingText}>
              {t('recordings.uploading')}
            </Text>
          </View>
        ) : null}
      </View>

      {isOnline && isLoggedIn && filesQ.isPending && (
        <ActivityIndicator size={'large'} />
      )}

      <FlatList
        data={allRecordings}
        keyExtractor={item => item.id}
        contentContainerStyle={[
          styles.listContent,
          { paddingBottom: insets.paddingBottom + 120 },
        ]}
        renderItem={renderItem}
        ItemSeparatorComponent={<View style={styles.recordingListSeparator} />}
        onEndReached={() => {
          if (isOnline && filesQ.hasNextPage && !filesQ.isFetchingNextPage) {
            filesQ.fetchNextPage();
          }
        }}
        refreshing={isOnline ? filesQ.isRefetching : undefined}
        onRefresh={
          isOnline
            ? () => queryClient.invalidateQueries({ queryKey: [keys.files] })
            : undefined
        }
        ListFooterComponent={
          isOnline && !filesQ.isPending ? (
            filesQ.hasNextPage ? (
              <ActivityIndicator />
            ) : (
              <Text style={styles.listFooter}>
                {t('recordings.listFooter')}
              </Text>
            )
          ) : undefined
        }
      />

      <View
        style={[
          styles.startRecordingPositioner,
          { bottom: insets.paddingBottom + 16 },
        ]}
      >
        <View style={styles.startRecordingContainer}>
          <Pressable
            style={({ pressed }) => [
              styles.startRecordingButton,
              pressed && styles.startRecordingButtonPressed,
            ]}
            onPress={handleStartRecording}
          >
            <RecordIcon width={24} height={24} />
            <Text style={styles.startRecordingButtonText}>
              {t('home.newRecording')}
            </Text>
          </Pressable>

          <View style={styles.consentRow}>
            <Text style={styles.consentText}>{t('home.consentNotice')}</Text>
          </View>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#ffffff',
  },
  topBar: {
    paddingHorizontal: 16,
    paddingBottom: 14,
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
  loginHelperText: {
    fontSize: 14,
    color: '#555E74',
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
    backgroundColor: '#FFEEDF',
    borderColor: '#FFCA9C',
  },
  networkText: {
    fontSize: 14,
    fontWeight: 500,
  },
  offlineText: {
    color: '#984800',
  },
  uploadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  uploadingText: {
    color: '#1F2937',
    fontWeight: '600',
    fontSize: 14,
  },
  listContent: {
    paddingVertical: 10,
    paddingHorizontal: 12,
  },
  recordingListSeparator: {
    height: 1,
    backgroundColor: '#DFE2EA',
    marginVertical: 4,
    marginHorizontal: 12,
  },
  listFooter: {
    color: '#6B7280',
    fontSize: 14,
    textAlign: 'center',
    paddingVertical: 12,
    paddingBottom: 14,
  },
  itemCard: {
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 8,
  },
  itemCardPressed: {
    backgroundColor: '#F3F4F6',
  },
  itemHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-start',
    gap: 4,
  },
  notAvailable: {
    color: '#626A80',
  },
  cardHeaderLeft: {
    width: 50,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  cardHeaderRight: {
    flex: 1,
    gap: 6,
  },
  syncStatusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  syncDotPending: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: '#F59E0B',
  },
  syncLabel: {
    color: '#92400E',
    fontWeight: '700',
    fontSize: 12,
  },
  recordingTitle: {
    color: '#111827',
    fontWeight: '700',
    fontSize: 14,
    lineHeight: 14,
  },
  recordingTitleSkeleton: {
    width: 140,
    height: 14,
    borderRadius: 6,
    backgroundColor: '#EEF1F4',
  },
  meta: {
    color: '#6B7280',
    fontSize: 12,
    lineHeight: 12,
  },
  metaSkeleton: {
    width: 100,
    height: 12,
    borderRadius: 6,
    backgroundColor: '#EEF1F4',
  },
  startRecordingPositioner: {
    position: 'absolute',
    width: '100%',
    display: 'flex',
    alignItems: 'center',
    paddingHorizontal: 16,
  },
  startRecordingContainer: {
    width: '100%',
    maxWidth: 400,
    paddingHorizontal: 20,
    padding: 14,
    gap: 8,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    borderRadius: 8,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#D9DCE3',
    boxShadow: [
      {
        blurRadius: 20,
        spreadDistance: 15,
        color: 'white',
        offsetX: 0,
        offsetY: 5,
      },
    ],
  },
  startRecordingButton: {
    backgroundColor: '#FFDAD7',
    borderRadius: 4,
    minHeight: 40,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 10,
    width: '100%',
  },
  startRecordingButtonPressed: {
    backgroundColor: '#ffd2cf',
  },
  startRecordingButtonText: {
    color: '#BD0F23',
    fontSize: 16,
    fontWeight: '700',
    fontFamily: 'Marianne',
  },
  consentRow: {
    gap: 12,
  },
  consentText: {
    flexShrink: 1,
    fontSize: 12,
    fontFamily: 'Marianne',
    fontWeight: '500',
    color: '#626A80',
    textAlign: 'center',
  },
});
