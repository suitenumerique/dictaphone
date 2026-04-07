import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useTranslation } from 'react-i18next';
import { useFocusEffect } from '@react-navigation/native';
import Sound from 'react-native-nitro-sound';
import { AudioPlayer, type AudioPlayerViewState } from '../components/AudioPlayer';
import { login } from '../services/authService';
import { deleteRecording, getRecordings } from '../services/storage';
import type { Recording } from '../types/recording';
import { Lucide } from '@react-native-vector-icons/lucide';
import { SafeAreaView } from 'react-native-screens/experimental';

type PlaybackStateById = Record<string, AudioPlayerViewState>;

const formatDurationLabel = (durationMs: number) => {
  const totalSeconds = Math.max(0, Math.floor(durationMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
};

const createDefaultPlayerState = (durationMs: number): AudioPlayerViewState => ({
  durationMs,
  isLoading: false,
  isPaused: false,
  isPlaying: false,
  positionMs: 0,
});

export default function RecordingsScreen() {
  const { t, i18n } = useTranslation();
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [playbackStateById, setPlaybackStateById] = useState<PlaybackStateById>({});
  const [isLoginLoading, setIsLoginLoading] = useState(false);
  const activeRecordingIdRef = useRef<string | null>(null);

  const dateFormatter = useMemo(() => new Intl.DateTimeFormat(i18n.language, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }), [i18n.language]);

  const clearPlaybackListeners = () => {
    Sound.removePlayBackListener();
    Sound.removePlaybackEndListener();
  };

  const updatePlaybackState = (recordingId: string, updater: (current: AudioPlayerViewState) => AudioPlayerViewState) => {
    setPlaybackStateById(prev => {
      const current = prev[recordingId] ?? createDefaultPlayerState(0);
      return {
        ...prev,
        [recordingId]: updater(current),
      };
    });
  };

  const attachPlaybackListeners = (recordingId: string) => {
    clearPlaybackListeners();

    Sound.addPlayBackListener(playback => {
      updatePlaybackState(recordingId, current => ({
        ...current,
        durationMs: Math.max(current.durationMs, Math.floor(playback.duration)),
        positionMs: Math.floor(playback.currentPosition),
      }));
    });

    Sound.addPlaybackEndListener(() => {
      updatePlaybackState(recordingId, current => ({
        ...current,
        isLoading: false,
        isPaused: false,
        isPlaying: false,
        positionMs: 0,
      }));
      activeRecordingIdRef.current = null;
      clearPlaybackListeners();
    });
  };

  const stopActiveRecording = async ({ preservePosition }: { preservePosition: boolean }) => {
    const activeRecordingId = activeRecordingIdRef.current;
    if (!activeRecordingId) {
      return;
    }

    await Sound.stopPlayer();
    clearPlaybackListeners();

    updatePlaybackState(activeRecordingId, current => ({
      ...current,
      isLoading: false,
      isPaused: preservePosition,
      isPlaying: false,
      positionMs: preservePosition ? current.positionMs : 0,
    }));

    activeRecordingIdRef.current = null;
  };

  const loadRecordings = useCallback(() => {
    const nextRecordings = getRecordings();
    setRecordings(nextRecordings);

    setPlaybackStateById(prev => {
      const next: PlaybackStateById = {};
      nextRecordings.forEach(recording => {
        next[recording.id] = prev[recording.id] ?? createDefaultPlayerState(recording.duration);
      });
      return next;
    });
  }, []);

  useEffect(() => {
    loadRecordings();
  }, [loadRecordings]);

  useFocusEffect(
    useCallback(() => {
      loadRecordings();
    }, [loadRecordings]),
  );

  useEffect(() => {
    return () => {
      clearPlaybackListeners();
      Sound.stopPlayer().catch(() => undefined);
    };
  }, []);

  const withLoading = async (recordingId: string, operation: () => Promise<void>) => {
    updatePlaybackState(recordingId, current => ({ ...current, isLoading: true }));
    try {
      await operation();
    } catch (error) {
      console.error('Playback operation failed:', error);
    } finally {
      updatePlaybackState(recordingId, current => ({ ...current, isLoading: false }));
    }
  };

  const handleTogglePlay = async (recording: Recording) => {
    const playerState = playbackStateById[recording.id] ?? createDefaultPlayerState(recording.duration);

    await withLoading(recording.id, async () => {
      const activeRecordingId = activeRecordingIdRef.current;

      if (activeRecordingId && activeRecordingId !== recording.id) {
        await stopActiveRecording({ preservePosition: true });
      }

      if (activeRecordingId === recording.id && playerState.isPlaying) {
        await Sound.pausePlayer();
        updatePlaybackState(recording.id, current => ({
          ...current,
          isPaused: true,
          isPlaying: false,
        }));
        return;
      }

      if (activeRecordingId === recording.id && playerState.isPaused) {
        await Sound.resumePlayer();
        updatePlaybackState(recording.id, current => ({
          ...current,
          isPaused: false,
          isPlaying: true,
        }));
        return;
      }

      await Sound.startPlayer(recording.filePath);
      attachPlaybackListeners(recording.id);

      if (playerState.positionMs > 0) {
        await Sound.seekToPlayer(playerState.positionMs);
      }

      activeRecordingIdRef.current = recording.id;
      updatePlaybackState(recording.id, current => ({
        ...current,
        durationMs: Math.max(current.durationMs, recording.duration),
        isPaused: false,
        isPlaying: true,
      }));
    });
  };

  const handleStop = async (recording: Recording) => {
    await withLoading(recording.id, async () => {
      if (activeRecordingIdRef.current === recording.id) {
        await stopActiveRecording({ preservePosition: false });
      }

      updatePlaybackState(recording.id, current => ({
        ...current,
        isPaused: false,
        isPlaying: false,
        positionMs: 0,
      }));
    });
  };

  const handleSeek = async (recording: Recording, positionMs: number) => {
    updatePlaybackState(recording.id, current => ({
      ...current,
      positionMs,
    }));

    if (activeRecordingIdRef.current !== recording.id) {
      return;
    }

    try {
      await Sound.seekToPlayer(positionMs);
    } catch (error) {
      console.error('Seek failed:', error);
    }
  };

  const handleDelete = (recording: Recording) => {
    Alert.alert(
      t('recordings.deleteTitle'),
      t('recordings.deleteMessage'),
      [
        {
          style: 'cancel',
          text: t('recordings.deleteCancel'),
        },
        {
          style: 'destructive',
          text: t('recordings.deleteConfirm'),
          onPress: async () => {
            if (activeRecordingIdRef.current === recording.id) {
              await stopActiveRecording({ preservePosition: false });
            }
            const nextRecordings = deleteRecording(recording.id);
            setRecordings(nextRecordings);
            setPlaybackStateById(prev => {
              const rest = { ...prev };
              delete rest[recording.id];
              return rest;
            });
          },
        },
      ],
    );
  };

  const handleLogin = async () => {
    setIsLoginLoading(true);
    try {
      await login();
    } catch (error) {
      console.error('Login failed:', error);
    } finally {
      setIsLoginLoading(false);
    }
  };

  const renderItem = ({ item }: { item: Recording }) => {
    const playerState = playbackStateById[item.id] ?? createDefaultPlayerState(item.duration);

    return (
      <View style={styles.card}>
        <View style={styles.cardHeader}>
          <View style={styles.cardHeaderLeft}>
            <Text style={styles.name}>{item.name}</Text>
            <Text style={styles.meta}>
              {dateFormatter.format(new Date(item.createdAt))} • {formatDurationLabel(item.duration)}
            </Text>
          </View>

          <View style={styles.headerActions}>
            <View style={styles.syncStatusRow}>
              <View style={[styles.syncDot, item.synced ? styles.syncDotOk : styles.syncDotPending]} />
              <Text style={styles.syncLabel}>{item.synced ? t('recordings.synced') : t('recordings.notSynced')}</Text>
            </View>

            <Pressable style={styles.deleteButton} onPress={() => handleDelete(item)}>
              <Text style={styles.deleteButtonText}><Lucide name="trash-2"/></Text>
            </Pressable>
          </View>
        </View>

        <AudioPlayer
          onSeek={position => handleSeek(item, position)}
          onStop={() => handleStop(item)}
          onTogglePlay={() => handleTogglePlay(item)}
          state={playerState}
        />
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.topBar}>
        <Pressable
          style={[styles.loginButton, isLoginLoading && styles.buttonDisabled]}
          onPress={handleLogin}
          disabled={isLoginLoading}
        >
          <Text style={styles.loginButtonText}>
            {t('recordings.loginButton')}
          </Text>
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
  },
  loginButton: {
    borderRadius: 10,
    backgroundColor: '#111827',
    paddingVertical: 12,
    alignItems: 'center',
  },
  loginButtonText: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '700',
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  listContent: {
    paddingVertical: 10,
    paddingHorizontal: 16,
    gap: 12,
  },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 14,
    padding: 14,
    gap: 12,
    shadowColor: '#111827',
    shadowOpacity: 0.08,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 3 },
    elevation: 3,
  },
  cardHeader: {
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
  syncStatusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  syncDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  syncDotOk: {
    backgroundColor: '#10B981',
  },
  syncDotPending: {
    backgroundColor: '#F59E0B',
  },
  syncLabel: {
    fontSize: 12,
    color: '#4B5563',
    fontWeight: '600',
  },
  deleteButton: {
    borderRadius: 8,
    backgroundColor: '#FEE2E2',
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  deleteButtonText: {
    color: '#B91C1C',
    fontWeight: '700',
    fontSize: 12,
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
