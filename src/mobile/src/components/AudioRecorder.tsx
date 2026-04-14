import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useTranslation } from 'react-i18next';
import { Lucide } from '@react-native-vector-icons/lucide';
import {
  AudioManager,
  AudioRecorder as AudioRecorderApi,
  FileFormat,
  FilePreset,
  RecordingNotificationManager,
} from 'react-native-audio-api';
import { formatDuration } from '@/features/recordings/utils/formatDuration';
// @ts-ignore
import RecordIcon from '@/assets/icons/record.svg';

type RecordingResult = {
  createdAt: string;
  durationMs: number;
  filePath: string;
};

type AudioRecorderProps = {
  onRecordingComplete?: (recording: RecordingResult) => void;
};

AudioManager.setAudioSessionOptions({
  iosCategory: 'record',
  iosMode: 'default',
  iosOptions: ['defaultToSpeaker', 'allowBluetoothA2DP'],
});

const audioRecorder = new AudioRecorderApi();

export const AudioRecorder = ({ onRecordingComplete }: AudioRecorderProps) => {
  const { t } = useTranslation();
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [recordingTimeMs, setRecordingTimeMs] = useState(0);

  const recordTimeLabel = useMemo(
    () => formatDuration(recordingTimeMs),
    [recordingTimeMs],
  );

  const recordingDurationInterval = useRef<ReturnType<
    typeof setTimeout
  > | null>(null);

  const updateNotification = (paused: boolean) => {
    RecordingNotificationManager.show({ paused });
  };

  const setupNotification = (paused: boolean) => {
    RecordingNotificationManager.show({
      title: 'Recording Demo',
      contentText: paused ? 'Paused recording' : 'Recording...',
      paused,
      smallIconResourceName: 'logo',
      pauseIconResourceName: 'pause',
      resumeIconResourceName: 'resume',
      color: 0xff6200,
    });
  };

  useEffect(() => {
    AudioManager.requestRecordingPermissions().then(res => {
      if (res === 'Granted') {
        audioRecorder.enableFileOutput({
          format: FileFormat.M4A,
          preset: FilePreset.High,
        });
      }
    });

    return () => {
      audioRecorder.stop();
      audioRecorder.disableFileOutput();
      AudioManager.setAudioSessionActivity(false);
      RecordingNotificationManager.hide();
    };
  }, []);

  useEffect(() => {
    if (!isRecording || isPaused) {
      if (recordingDurationInterval.current) {
        clearInterval(recordingDurationInterval.current);
        recordingDurationInterval.current = null;
      }
      return;
    }

    if (!recordingDurationInterval.current) {
      recordingDurationInterval.current = setInterval(() => {
        try {
          const duration = audioRecorder.getCurrentDuration();
          setRecordingTimeMs(duration * 1000);
        } catch (error) {
          console.error('Failed to get current recording duration:', error);
        }
      }, 200);
    }

    return () => {
      if (recordingDurationInterval.current) {
        clearInterval(recordingDurationInterval.current);
      }
    };
  }, [isPaused, isRecording]);

  const onStartRecord = useCallback(async () => {
    const permissions = await AudioManager.requestRecordingPermissions();
    if (permissions !== 'Granted') {
      console.warn('Permissions are not granted');
      return;
    }

    setIsLoading(true);
    try {
      const success = await AudioManager.setAudioSessionActivity(true);
      if (!success) {
        console.warn('Could not activate the audio session');
        return;
      }

      const result = audioRecorder.start();
      if (result.status === 'error') {
        console.warn(result.message);
        return;
      }

      setupNotification(false);
      setRecordingTimeMs(0);
      setIsRecording(true);
      setIsPaused(false);
    } catch (error) {
      console.error('Failed to start recording:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const onPauseRecord = useCallback(async () => {
    setIsLoading(true);
    try {
      audioRecorder.pause();
      setIsPaused(true);
      updateNotification(true);
    } catch (error) {
      console.error('Failed to pause recording:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const onResumeRecord = useCallback(async () => {
    setIsLoading(true);
    try {
      audioRecorder.resume();
      updateNotification(false);
      setIsPaused(false);
    } catch (error) {
      console.error('Failed to resume recording:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const onStopRecord = useCallback(async () => {
    setIsLoading(true);
    try {
      const result = audioRecorder.stop();
      await RecordingNotificationManager.hide();
      if (result.status === 'error') {
        console.warn(result.message);
        return;
      }

      setIsRecording(false);
      setIsPaused(false);
      await AudioManager.setAudioSessionActivity(false);

      onRecordingComplete?.({
        createdAt: new Date().toISOString(),
        durationMs: result.duration * 1000,
        filePath: result.path,
      });

      setRecordingTimeMs(0);
    } catch (error) {
      console.error('Failed to stop recording:', error);
    } finally {
      setIsLoading(false);
    }
  }, [onRecordingComplete]);

  useEffect(() => {
    const pauseListener = RecordingNotificationManager.addEventListener(
      'recordingNotificationPause',
      () => {
        onPauseRecord();
      },
    );

    const resumeListener = RecordingNotificationManager.addEventListener(
      'recordingNotificationResume',
      () => {
        onResumeRecord();
      },
    );

    return () => {
      pauseListener.remove();
      resumeListener.remove();
      RecordingNotificationManager.hide();
    };
  }, [onPauseRecord, onResumeRecord]);

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const onClearRecord = useCallback(async () => {
    setIsLoading(true);
    Alert.alert(t('recordings.deleteTitle'), t('recordings.deleteMessage'), [
      {
        style: 'cancel',
        text: t('recordings.deleteCancel'),
        onPress: () => {
          setIsLoading(false);
        },
      },
      {
        style: 'destructive',
        text: t('recordings.deleteConfirm'),
        onPress: async () => {
          try {
            audioRecorder.stop();
            setIsRecording(false);
            setIsPaused(false);
            setRecordingTimeMs(0);
          } finally {
            setIsLoading(false);
          }
        },
      },
    ]);
  }, [t]);

  if (!isRecording) {
    return (
      <View style={styles.idleContainer}>
        <Pressable
          style={styles.startRecordingButton}
          onPress={onStartRecord}
          disabled={isLoading}
        >
          {isLoading ? (
            <ActivityIndicator color="#FFFFFF" />
          ) : (
            <>
              <RecordIcon width={24} height={24}/>
              <Text style={styles.startRecordingButtonText}>
                {t('home.newRecording')}
              </Text>
            </>
          )}
        </Pressable>

        <View style={styles.consentRow}>
          <Text style={styles.consentText}>{t('home.consentNotice')}</Text>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.activeContainer}>
      <View style={styles.statusSection}>
        <View style={styles.statusBadge}>
          <Lucide name="audio-lines" size={18} color="#D62839" />
          <Text style={styles.statusTitle}>
            {t('home.recordingInProgress')}
          </Text>
        </View>

        <Text style={styles.statusSubtitle}>
          {t('home.transcriptAfterRecording')}
        </Text>
      </View>

      <View style={styles.timerSection}>
        <Text style={styles.timer}>{recordTimeLabel}</Text>
      </View>

      <View style={styles.controlsRow}>
        <Pressable
          style={[
            styles.controlButton,
            styles.pauseButton,
            isLoading && styles.buttonDisabled,
          ]}
          onPress={isPaused ? onResumeRecord : onPauseRecord}
          disabled={isLoading}
        >
          <Lucide
            name={isPaused ? 'play' : 'pause'}
            size={24}
            color="#475467"
          />
          <Text style={styles.pauseButtonText}>
            {isPaused ? t('home.resume') : t('home.pause')}
          </Text>
        </Pressable>

        <Pressable
          style={[
            styles.controlButton,
            styles.endButton,
            isLoading && styles.buttonDisabled,
          ]}
          onPress={onStopRecord}
          disabled={isLoading}
        >
          <Lucide name="stop-circle" size={24} color="#FFFFFF" />
          <Text style={styles.endButtonText}>{t('home.end')}</Text>
        </Pressable>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  idleContainer: {
    width: '100%',
    maxWidth: 430,
    borderRadius: 14,
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
    fontFamily: "Marianne",
  },
  consentRow: {
    gap: 12,
  },
  consentText: {
    flexShrink: 1,
    fontSize: 12,
    fontFamily: "Marianne",
    fontWeight: '500',
    color: '#626A80',
    textAlign: 'center',
  },
  activeContainer: {
    display: 'flex',
    flexDirection: 'column',
    gap: 30,
    width: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    paddingTop: 36,
    paddingBottom: 20,
  },
  statusSection: {
    alignItems: 'center',
    gap: 12,
  },
  statusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  statusTitle: {
    fontSize: 28,
    fontWeight: '700',
    color: '#D62839',
  },
  statusSubtitle: {
    color: '#667085',
    fontSize: 16,
    textAlign: 'center',
    maxWidth: 320,
    lineHeight: 22,
  },
  timerSection: {
    width: '100%',
    justifyContent: 'center',
    alignItems: 'center',
  },
  timer: {
    fontSize: 74,
    fontWeight: '800',
    color: '#1D2433',
    fontVariant: ['tabular-nums'],
    lineHeight: 80,
  },
  controlsRow: {
    flexDirection: 'row',
    width: '100%',
    justifyContent: 'center',
    gap: 14,
  },
  controlButton: {
    flex: 1,
    minHeight: 46,
    borderRadius: 10,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
  },
  pauseButton: {
    backgroundColor: '#D9DEE7',
  },
  endButton: {
    backgroundColor: '#D62839',
  },
  pauseButtonText: {
    color: '#475467',
    fontSize: 18,
    fontWeight: '600',
  },
  endButtonText: {
    color: '#FFFFFF',
    fontSize: 18,
    fontWeight: '700',
  },
  buttonDisabled: {
    opacity: 0.7,
  },
});
