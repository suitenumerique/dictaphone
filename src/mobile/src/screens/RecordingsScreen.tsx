import React, { useMemo } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Linking,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useTranslation } from 'react-i18next';
import type { Recording } from '../types/recording';
import { Lucide } from '@react-native-vector-icons/lucide';
import { SafeAreaView } from 'react-native-screens/experimental';
import { InAppBrowser } from 'react-native-inappbrowser-reborn';
import { BASE_URL } from '@/api/constants';
import { useLocalRecordings } from '@/features/recordings/hooks/useLocalRecordings';
import { UserInfoCard } from '@/components/UserInfoCard';

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
  const {
    recordings,
    isUploading,
    recordingIdBeingUploaded,
  } = useLocalRecordings();
  const dateFormatter = useMemo(
    () =>
      new Intl.DateTimeFormat(i18n.language, {
        dateStyle: 'medium',
        timeStyle: 'short',
      }),
    [i18n.language],
  );

  const handleOpenWebRecordings = async () => {
    try {
      const available = await InAppBrowser.isAvailable();
      if (available) {
        await InAppBrowser.open(BASE_URL, {
          animated: true,
          dismissButtonStyle: 'close',
          enableDefaultShare: false,
          forceCloseOnRedirection: false,
          showTitle: true,
          toolbarColor: '#111827',
        });
        return;
      }

      await Linking.openURL(BASE_URL);
    } catch (error) {
      console.error('Failed to open recordings page:', error);
    }
  };

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

          <View style={styles.headerActions}>
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
      </View>
    );
  };

  return (
    <SafeAreaView edges={{ bottom: true, top: true }} style={styles.container}>
      <View style={styles.topBar}>
        <UserInfoCard />
        <Pressable
          style={styles.manageButton}
          onPress={handleOpenWebRecordings}
        >
          <Lucide name="external-link" size={16} color="#FFFFFF" />
          <Text style={styles.manageButtonText}>
            {t('recordings.manageOnline')}
          </Text>
        </Pressable>

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
          <Pressable
            style={styles.retryButton}
            // onPress={() => retryPendingUploads().catch(() => undefined)}
          >
            <Lucide name="refresh-cw" size={15} color="#1D4ED8" />
          </Pressable>
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
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingTop: 36,
    backgroundColor: '#F9FAFB',
  },
  topBar: {
    paddingTop: 16,
    paddingHorizontal: 16,
    paddingBottom: 8,
    gap: 12,
  },
  manageButton: {
    borderRadius: 10,
    backgroundColor: '#111827',
    paddingVertical: 12,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  manageButtonText: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '700',
  },
  playerCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 14,
    padding: 14,
    gap: 10,
    shadowColor: '#111827',
    shadowOpacity: 0.08,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 3 },
    elevation: 3,
  },
  playerTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#111827',
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
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  pendingTitle: {
    color: '#111827',
    fontWeight: '700',
    fontSize: 16,
  },
  retryButton: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#EFF6FF',
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  listContent: {
    paddingVertical: 10,
    paddingHorizontal: 12,
    gap: 12,
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
  headerActions: {
    alignItems: 'flex-end',
    gap: 8,
  },
  rowActions: {
    flexDirection: 'row',
    gap: 8,
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
    fontSize: 12,
    color: '#4B5563',
    fontWeight: '600',
  },
  playRecordingButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#E0F2FE',
    alignItems: 'center',
    justifyContent: 'center',
  },
  deleteButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  name: {
    fontSize: 18,
    fontWeight: '700',
    color: '#111827',
  },
  meta: {
    fontSize: 14,
    color: '#6B7280',
  },
  emptyContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 24,
    minHeight: 200,
  },
  emptyTitle: {
    color: '#111827',
    fontWeight: '700',
    fontSize: 22,
    marginBottom: 8,
  },
  emptySubtitle: {
    color: '#6B7280',
    fontSize: 16,
    textAlign: 'center',
  },
});
