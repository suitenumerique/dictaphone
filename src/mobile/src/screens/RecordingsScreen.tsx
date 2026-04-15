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
import type { Recording } from '../types/recording';
import { SafeAreaView } from 'react-native-screens/experimental';
import { useLocalRecordings } from '@/features/recordings/hooks/useLocalRecordings';
import { Lucide } from '@react-native-vector-icons/lucide';
import { useNetInfo } from '@react-native-community/netinfo';
import { useNavigation } from '@react-navigation/core';
// @ts-ignore
import LogoWithName from '../assets/logo-with-name.svg';
// @ts-ignore
import RecordIcon from '@/assets/icons/record.svg';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

const formatDurationLabel = (durationMs: number) => {
  const totalSeconds = Math.max(0, Math.floor(durationMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(
    2,
    '0',
  )}`;
};

export default function RecordingsScreen() {
  const { t, i18n } = useTranslation();
  const netInfo = useNetInfo();
  const navigation = useNavigation();
  const safeAreaInsets = useSafeAreaInsets();
  const { recordings, isUploading, recordingIdBeingUploaded } =
    useLocalRecordings();

  const handleStartRecording = useCallback(() => {
    // @ts-ignore
    navigation.navigate('RecordingInProgress');
  }, [navigation]);

  const isOnline =
    netInfo.isConnected === true && netInfo.isInternetReachable !== false;

  const dateFormatter = useMemo(
    () =>
      new Intl.DateTimeFormat(i18n.language, {
        dateStyle: 'medium',
        timeStyle: 'short',
      }),
    [i18n.language],
  );

  const renderItem = ({ item }: { item: Recording }) => {
    return (
      <View style={styles.itemCard}>
        <View style={styles.itemHeader}>
          <View style={styles.cardHeaderLeft}>
            <Text style={styles.name}>{item.name}</Text>
            <Text style={styles.meta}>
              {dateFormatter.format(new Date(item.createdAt))} •{' '}
              {formatDurationLabel(item.durationMs)}
            </Text>
          </View>

          <View style={styles.syncStatusRow}>
            <View style={styles.syncDotPending} />
            <Text style={styles.syncLabel}>
              {recordingIdBeingUploaded === item.id
                ? t('recordings.uploading')
                : t('recordings.notSynced')}
            </Text>
          </View>
        </View>
      </View>
    );
  };

  return (
    <SafeAreaView edges={{ top: true }} style={styles.container}>
      <View style={styles.topBar}>
        <LogoWithName style={styles.title} />

        {!isOnline && (
          <View style={[styles.networkCard, styles.offlineCard]}>
            <Lucide name={'wifi-off'} size={16} color={'#991B1B'} />
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

      <View style={styles.pendingCard}>
        <View style={styles.pendingHeader}>
          <Text style={styles.pendingTitle}>
            {t('recordings.pendingTitle')}
          </Text>
        </View>

        {recordings.length === 0 ? (
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyTitle}>{t('recordings.emptyTitle')}</Text>
            <Text style={styles.emptySubtitle}>
              {t('recordings.emptySubtitle')}
            </Text>
          </View>
        ) : (
          <FlatList
            data={recordings}
            keyExtractor={item => item.id}
            contentContainerStyle={styles.listContent}
            renderItem={renderItem}
          />
        )}
      </View>

      <View
        style={[
          styles.startRecordingPositionner,
          { bottom: safeAreaInsets.bottom + 16 },
        ]}
      >
        <View style={styles.startRecordingContainer}>
          <Pressable
            style={styles.startRecordingButton}
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
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F9FAFB',
  },
  topBar: {
    paddingTop: 16,
    paddingHorizontal: 16,
    paddingBottom: 8,
    gap: 12,
  },
  title: {
    marginBottom: 2,
  },
  networkCard: {
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: 1,
  },
  offlineCard: {
    backgroundColor: '#FEF2F2',
    borderColor: '#FECACA',
  },
  networkText: {
    fontSize: 14,
    fontWeight: '600',
  },
  onlineText: {
    color: '#065F46',
  },
  offlineText: {
    color: '#991B1B',
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
  pendingCard: {
    flex: 1,
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    marginHorizontal: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#E5E7EB',
    overflow: 'hidden',
  },
  pendingHeader: {
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#F1F5F9',
  },
  pendingTitle: {
    color: '#111827',
    fontWeight: '700',
    fontSize: 16,
  },
  listContent: {
    paddingVertical: 10,
    paddingHorizontal: 12,
    gap: 12,
    paddingBottom: 130,
  },
  itemCard: {
    backgroundColor: '#FFFFFF',
    paddingVertical: 14,
    paddingHorizontal: 12,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#F1F5F9',
  },
  itemHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 10,
  },
  cardHeaderLeft: {
    flex: 1,
    gap: 4,
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
  name: {
    color: '#111827',
    fontWeight: '700',
    fontSize: 15,
  },
  meta: {
    color: '#6B7280',
    fontSize: 13,
  },
  emptyContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 20,
    gap: 8,
  },
  emptyTitle: {
    color: '#111827',
    fontWeight: '700',
    fontSize: 18,
  },
  emptySubtitle: {
    color: '#6B7280',
    fontSize: 14,
    textAlign: 'center',
  },
  startRecordingPositionner: {
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
    borderRadius: 8,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#D9DCE3',
    padding: 14,
    gap: 8,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
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
