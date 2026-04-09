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
  Animated,
  Easing,
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

type RecordingResult = {
  createdAt: string;
  duration: number;
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
audioRecorder.enableFileOutput({
  format: FileFormat.M4A,
  preset: FilePreset.High,
});

const formatDuration = (durationMs: number) => {
  const totalSeconds = Math.floor(durationMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(
    2,
    '0',
  )}`;
}


export const AudioRecorder = ({ onRecordingComplete }: AudioRecorderProps) => {
  const { t } = useTranslation();
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [recordingTimeMs, setRecordingTimeMs] = useState(0);
  const recordTimeLabel = useMemo(() => formatDuration(recordingTimeMs), [recordingTimeMs]);
  const pulse = useRef(new Animated.Value(1)).current;
  const recordingDurationInterval = useRef<ReturnType<
    typeof setTimeout
  > | null>(null);

  const updateNotification = (paused: boolean) => {
    RecordingNotificationManager.show({
      paused,
    });
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
    return () => {
      audioRecorder.stop();
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
      if (recordingDurationInterval.current)
        clearInterval(recordingDurationInterval.current);
    };
  }, [isPaused, isRecording]);

  const recordActionLabel = useMemo(() => {
    if (isLoading) {
      return '';
    }
    if (isPaused) {
      return t('home.resume');
    }
    if (isRecording) {
      return t('home.pause');
    }
    return t('home.record');
  }, [isLoading, isPaused, isRecording, t]);

  useEffect(() => {
    if (!isRecording || isPaused) {
      pulse.stopAnimation();
      pulse.setValue(1);
      return;
    }

    Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: 1.05,
          duration: 700,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: 1,
          duration: 700,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
      ]),
    ).start();
  }, [isPaused, isRecording, pulse]);

  const onStartRecord = useCallback(async () => {
    const permissions = await AudioManager.requestRecordingPermissions();
    if (permissions !== 'Granted') {
      console.warn('Permissions are not granted');
      return;
    }

    setIsLoading(true);
    try {
      // Activate audio session
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

      console.log('Recording started to file:', result.path);
      setIsRecording(true);

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
        duration: result.duration * 1000,
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
        console.log('Notification pause action received');
        onPauseRecord();
      },
    );

    const resumeListener = RecordingNotificationManager.addEventListener(
      'recordingNotificationResume',
      () => {
        console.log('Notification resume action received');
        onResumeRecord();
      },
    );

    return () => {
      pauseListener.remove();
      resumeListener.remove();
      RecordingNotificationManager.hide();
    };
  }, [onPauseRecord, onResumeRecord]);

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

  const recordAction = useCallback(() => {
    if (isLoading) {
      return;
    }
    if (isPaused) {
      onResumeRecord();
    } else if (isRecording) {
      onPauseRecord();
    } else {
      onStartRecord();
    }
  }, [
    isLoading,
    isPaused,
    isRecording,
    onPauseRecord,
    onResumeRecord,
    onStartRecord,
  ]);

  return (
    <View style={styles.container}>
      <Text style={styles.timer}>{recordTimeLabel}</Text>

      <Animated.View
        style={[styles.recordButtonOuter, { transform: [{ scale: pulse }] }]}
      >
        <Pressable
          style={[styles.recordButton, isRecording && styles.recordingButton]}
          onPress={recordAction}
          disabled={isLoading}
        >
          <Lucide name={'mic'} size={36} color="#FFFFFF" />
          <Text style={styles.recordButtonText}>{recordActionLabel}</Text>
        </Pressable>
      </Animated.View>

      <View style={styles.shortActions}>
        <Pressable
          style={[
            styles.actionButton,
            (!isPaused || isLoading) && styles.actionButtonDisabled,
          ]}
          onPress={onClearRecord}
          disabled={!isPaused || isLoading}
        >
          <Lucide name="eraser" size={36} />
        </Pressable>

        <Pressable
          style={[
            styles.actionButton,
            (!isRecording || isLoading) && styles.actionButtonDisabled,
          ]}
          onPress={onStopRecord}
          disabled={!isRecording || isLoading}
        >
          <Lucide name="save" size={36} />
          <Text>{t('home.save')}</Text>
        </Pressable>
      </View>

      {isLoading && <ActivityIndicator />}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    gap: 20,
  },
  timer: {
    fontSize: 48,
    fontWeight: '700',
    color: '#111827',
    minWidth: 140,
    textAlign: 'center',
    fontVariant: ['tabular-nums'],
  },
  recordButtonOuter: {
    borderRadius: 100,
  },
  recordButton: {
    width: 170,
    height: 170,
    borderRadius: 85,
    backgroundColor: '#DC2626',
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#DC2626',
    shadowOpacity: 0.35,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 8 },
    elevation: 8,
  },
  recordingButton: {
    backgroundColor: '#DC2626',
  },
  recordButtonText: {
    color: '#FFFFFF',
    fontWeight: '700',
    fontSize: 24,
  },
  shortActions: {
    flexDirection: 'row',
    gap: 12,
  },
  actionButton: {
    display: 'flex',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderRadius: 12,
    backgroundColor: '#E5E7EB',
    paddingHorizontal: 12,
    paddingVertical: 12,
  },
  actionButtonDisabled: {
    opacity: 0.6,
  },
  pauseButtonText: {
    color: '#1F2937',
    fontSize: 18,
    fontWeight: '600',
  },
});
