import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
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
import {
  PlayerQueue,
  type TrackItem,
  TrackPlayer,
  useOnChangeTrack,
  useOnPlaybackProgressChange,
  useOnPlaybackStateChange,
} from 'react-native-nitro-player';
import {
  AudioPlayer,
  type AudioPlayerViewState,
} from '../components/AudioPlayer';
import { login } from '../services/authService';
import { deleteRecording, getRecordings } from '../services/storage';
import type { Recording } from '../types/recording';
import { Lucide } from '@react-native-vector-icons/lucide';
import { SafeAreaView } from 'react-native-screens/experimental';
import { LoginWithProConnectButton } from '../components/LoginWithProConnectButton';

const RECORDINGS_PLAYLIST_NAME = 'Dictaphone Recordings';

const formatDurationLabel = (durationMs: number) => {
  const totalSeconds = Math.max(0, Math.floor(durationMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(
    2,
    '0',
  )}`;
};

const toTrackItem = (recording: Recording): TrackItem => ({
  id: recording.id,
  title: recording.name,
  artist: 'Dictaphone',
  album: 'Recordings',
  duration: Math.max(1, Math.floor(recording.duration / 1000)),
  url: recording.filePath,
});

export default function RecordingsScreen() {
  const { t, i18n } = useTranslation();

  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [isLoginLoading, setIsLoginLoading] = useState(false);
  const [isPlayerBusy, setIsPlayerBusy] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);

  const playlistIdRef = useRef<string | null>(null);
  const isPlayerConfiguredRef = useRef(false);
  const isPlayerConfigInFlightRef = useRef<Promise<void> | null>(null);

  const { track: currentTrack } = useOnChangeTrack();
  const { state: playbackState } = useOnPlaybackStateChange();
  const { position, totalDuration } = useOnPlaybackProgressChange();

  const dateFormatter = useMemo(
    () =>
      new Intl.DateTimeFormat(i18n.language, {
        dateStyle: 'medium',
        timeStyle: 'short',
      }),
    [i18n.language],
  );

  const activeRecording = useMemo(
    () =>
      recordings.find(recording => recording.id === currentTrack?.id) ?? null,
    [recordings, currentTrack?.id],
  );

  const currentPlayerState = useMemo<AudioPlayerViewState>(
    () => ({
      durationMs: Math.max(
        Math.floor(totalDuration * 1000),
        activeRecording?.duration ?? 0,
      ),
      isLoading: isPlayerBusy,
      isPaused: playbackState === 'paused',
      isPlaying: playbackState === 'playing',
      positionMs: Math.floor(position * 1000),
    }),
    [
      activeRecording?.duration,
      isPlayerBusy,
      playbackState,
      position,
      totalDuration,
    ],
  );

  const ensurePlayerConfigured = useCallback(async () => {
    if (isPlayerConfiguredRef.current) {
      return;
    }

    if (!isPlayerConfigInFlightRef.current) {
      isPlayerConfigInFlightRef.current = TrackPlayer.configure({
        androidAutoEnabled: false,
        carPlayEnabled: false,
        showInNotification: false,
      })
        .then(() => {
          isPlayerConfiguredRef.current = true;
        })
        .finally(() => {
          isPlayerConfigInFlightRef.current = null;
        });
    }

    await isPlayerConfigInFlightRef.current;
  }, []);

  const clearPlaybackPlaylist = useCallback(async () => {
    await TrackPlayer.pause().catch(() => undefined);

    const currentPlaylistId = playlistIdRef.current;
    if (!currentPlaylistId) {
      return;
    }

    await PlayerQueue.deletePlaylist(currentPlaylistId).catch(() => undefined);
    playlistIdRef.current = null;
  }, []);

  const loadRecordings = useCallback(() => {
    const nextRecordings = getRecordings();
    setRecordings(nextRecordings);
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
      clearPlaybackPlaylist().catch(() => undefined);
    };
  }, [clearPlaybackPlaylist]);

  useEffect(() => {
    if (!activeRecording) {
      return;
    }

    let isMounted = true;
    const syncPlaybackSpeed = async () => {
      try {
        await ensurePlayerConfigured();
        const speed = await TrackPlayer.getPlaybackSpeed();
        if (isMounted) {
          setPlaybackSpeed(speed);
        }
      } catch (error) {
        console.error('Failed to read playback speed:', error);
      }
    };

    syncPlaybackSpeed().catch(() => undefined);
    return () => {
      isMounted = false;
    };
  }, [activeRecording, ensurePlayerConfigured]);

  const handlePlayRecording = async (recording: Recording) => {
    setIsPlayerBusy(true);
    try {
      await ensurePlayerConfigured();
      await clearPlaybackPlaylist();

      const playlistId = await PlayerQueue.createPlaylist(
        RECORDINGS_PLAYLIST_NAME,
      );
      playlistIdRef.current = playlistId;

      const track = toTrackItem(recording);
      await PlayerQueue.addTrackToPlaylist(playlistId, track);
      await PlayerQueue.loadPlaylist(playlistId);
      await TrackPlayer.playSong(track.id, playlistId);
      await TrackPlayer.play();
    } catch (error) {
      console.error('Playback operation failed:', error);
    } finally {
      setIsPlayerBusy(false);
    }
  };

  const handleToggleCurrentTrack = async () => {
    if (!activeRecording) {
      return;
    }

    setIsPlayerBusy(true);
    try {
      await ensurePlayerConfigured();
      if (playbackState === 'playing') {
        await TrackPlayer.pause();
      } else {
        await TrackPlayer.play();
      }
    } catch (error) {
      console.error('Toggle play failed:', error);
    } finally {
      setIsPlayerBusy(false);
    }
  };

  const handleSeekCurrentTrack = async (positionMs: number) => {
    if (!activeRecording) {
      return;
    }

    try {
      await TrackPlayer.seek(positionMs / 1000);
    } catch (error) {
      console.error('Seek failed:', error);
    }
  };

  const handleSetPlaybackSpeed = async (speed: number) => {
    if (!activeRecording) {
      return;
    }

    try {
      await ensurePlayerConfigured();
      await TrackPlayer.setPlaybackSpeed(speed);
      setPlaybackSpeed(speed);
    } catch (error) {
      console.error('Set playback speed failed:', error);
    }
  };

  const handleDelete = (recording: Recording) => {
    Alert.alert(t('recordings.deleteTitle'), t('recordings.deleteMessage'), [
      {
        style: 'cancel',
        text: t('recordings.deleteCancel'),
      },
      {
        style: 'destructive',
        text: t('recordings.deleteConfirm'),
        onPress: async () => {
          if (currentTrack?.id === recording.id) {
            await clearPlaybackPlaylist();
          }

          const nextRecordings = deleteRecording(recording.id);
          setRecordings(nextRecordings);
        },
      },
    ]);
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
    return (
      <View style={styles.card}>
        <View style={styles.cardHeader}>
          <View style={styles.cardHeaderLeft}>
            <Text style={styles.name}>{item.name}</Text>
            <Text style={styles.meta}>
              {dateFormatter.format(new Date(item.createdAt))} •{' '}
              {formatDurationLabel(item.duration)}
            </Text>
          </View>

          <View style={styles.headerActions}>
            <View style={styles.syncStatusRow}>
              <View
                style={[
                  styles.syncDot,
                  item.synced ? styles.syncDotOk : styles.syncDotPending,
                ]}
              />
              <Text style={styles.syncLabel}>
                {item.synced
                  ? t('recordings.synced')
                  : t('recordings.notSynced')}
              </Text>
            </View>

            <View style={styles.rowActions}>
              <Pressable
                style={[
                  styles.playRecordingButton,
                  isPlayerBusy && styles.buttonDisabled,
                ]}
                onPress={() => handlePlayRecording(item)}
                disabled={isPlayerBusy}
              >
                <Lucide name="play" size={16} color="#1D4ED8" />
              </Pressable>

              <Pressable
                style={styles.deleteButton}
                onPress={() => handleDelete(item)}
              >
                <Text style={styles.deleteButtonText}>
                  <Lucide name="trash-2" size={16} />
                </Text>
              </Pressable>
            </View>
          </View>
        </View>
      </View>
    );
  };

  return (
    <SafeAreaView edges={{ bottom: true }} style={styles.container}>
      <View style={styles.topBar}>
        <LoginWithProConnectButton />

        {activeRecording ? (
          <View style={styles.playerCard}>
            <Text style={styles.playerTitle}>{activeRecording.name}</Text>
            <AudioPlayer
              onSeek={handleSeekCurrentTrack}
              onSetSpeed={handleSetPlaybackSpeed}
              onTogglePlay={handleToggleCurrentTrack}
              playbackSpeed={playbackSpeed}
              state={currentPlayerState}
            />
          </View>
        ) : null}
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
    paddingTop: 24,
    backgroundColor: '#F9FAFB',
  },
  topBar: {
    paddingTop: 16,
    paddingHorizontal: 16,
    paddingBottom: 8,
    gap: 12,
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
    paddingVertical: 14,
    paddingHorizontal: 12,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#F1F5F9', // subtle border instead of shadow
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
  rowActions: {
    flexDirection: 'row',
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
