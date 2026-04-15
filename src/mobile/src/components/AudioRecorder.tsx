import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';
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
import { useNavigation, usePreventRemove } from '@react-navigation/core';
import { PermissionStatus } from 'react-native-audio-api/lib/typescript/system/types';
import uuid from 'react-native-uuid';
import { useLocalRecordings } from '@/features/recordings/hooks/useLocalRecordings';

AudioManager.setAudioSessionOptions({
  iosCategory: 'record',
  iosMode: 'default',
  iosOptions: ['defaultToSpeaker', 'allowBluetoothA2DP'],
});

const audioRecorder = new AudioRecorderApi();

export const AudioRecorder = () => {
  const { t } = useTranslation();
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [recordingTimeMs, setRecordingTimeMs] = useState(0);
  const [permissionStatus, setPermissionStatus] =
    useState<PermissionStatus>('Undetermined');
  const { addRecording } = useLocalRecordings();
  const navigation = useNavigation();

  const recordTimeLabel = useMemo(
    () => formatDuration(recordingTimeMs),
    [recordingTimeMs],
  );

  const recordingDurationInterval = useRef<ReturnType<
    typeof setTimeout
  > | null>(null);

  const updateNotification = async (paused: boolean) => {
    await RecordingNotificationManager.show({ paused });
  };

  const setupNotification = async (paused: boolean) => {
    await RecordingNotificationManager.show({
      title: 'Recording Demo',
      contentText: paused ? 'Paused recording' : 'Recording...',
      paused,
      smallIconResourceName: 'logo',
      pauseIconResourceName: 'pause',
      resumeIconResourceName: 'resume',
      color: 0xff6200,
    });
  };

  const clearRecording = () => {
    audioRecorder.stop();
    audioRecorder.disableFileOutput();
    AudioManager.setAudioSessionActivity(false);
    RecordingNotificationManager.hide();
    // Todo delete file as option for when going back alert
  };

  useEffect(() => {
    // Todo properly manage permissions
    AudioManager.requestRecordingPermissions().then(res => {
      setPermissionStatus(res);
      if (res === 'Granted') {
        audioRecorder.enableFileOutput({
          format: FileFormat.M4A,
          preset: FilePreset.High,
        });
      }
    });

    return () => {
      clearRecording();
    };
  }, []);

  useEffect(() => {
    if (permissionStatus === 'Denied') {
      Alert.alert(
        'Permission Denied',
        'Recording permission is required to use this feature.',
        [
          {
            text: 'OK',
            onPress: () => {
              // Handle the "OK" button press
            },
          },
        ],
      );
    }
  }, [permissionStatus]);

  usePreventRemove(isRecording, ({ data }) => {
    Alert.alert('A recording is in progress.', 'Do you want to discard it?', [
      { text: "Don't leave", style: 'cancel', onPress: () => {} },
      {
        text: 'Discard',
        style: 'destructive',
        onPress: () => {
          clearRecording();
          navigation.dispatch(data.action);
        },
      },
    ]);
  });

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

  const handleStartRecording = useCallback(async () => {
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

  useEffect(() => {
    if (permissionStatus === 'Granted') {
      handleStartRecording();
    }
  }, [permissionStatus, handleStartRecording]);

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

      // TODO finish name
      const name = t('home.recordingName', {
        duration: formatDuration(result.duration * 1000),
      });
      addRecording({
        createdAt: new Date().toISOString(),
        durationMs: result.duration * 1000,
        filePath: result.path,
        name,
        id: uuid.v4(),
        uploadingStatus: 'to_upload',
      });
      navigation.navigate('Main' as never);

      setRecordingTimeMs(0);
    } catch (error) {
      console.error('Failed to stop recording:', error);
    } finally {
      setIsLoading(false);
    }
  }, [addRecording, navigation, t]);

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

  return (
    <View style={styles.activeContainer}>
      <View style={styles.statusSection}>
        <View style={styles.statusBadge}>
          {isPaused ? (
            <Lucide name="pause-circle" size={18} color="#555E74" />
          ) : (
            <Lucide name="audio-lines" size={18} color="#BD0F23" />
          )}
          <Text
            style={[styles.statusTitle, isPaused && styles.statusTitlePaused]}
          >
            {t(isPaused ? 'home.recordingPaused' : 'home.recordingInProgress')}
          </Text>
        </View>

        <Text style={styles.statusSubtitle}>
          {t(
            isPaused
              ? 'home.recordingSubtitlePaused'
              : 'home.recordingSubtitle',
          )}
        </Text>
      </View>

      <View style={styles.timerSection}>
        <Text style={[styles.timer, isPaused && styles.timerPaused]}>
          {recordTimeLabel}
        </Text>
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
  activeContainer: {
    height: '100%',
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
    fontSize: 14,
    fontWeight: 500,
    color: '#BD0F23',
  },
  statusTitlePaused: {
    color: '#555E74',
  },
  statusSubtitle: {
    color: '#667085',
    fontSize: 12,
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
    fontSize: 44,
    fontWeight: '800',
    color: '#1D2433',
    fontVariant: ['tabular-nums'],
    lineHeight: 80,
  },
  timerPaused: {
    color: '#626A80',
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
    fontSize: 16,
    fontWeight: '600',
  },
  endButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '700',
  },
  buttonDisabled: {
    opacity: 0.7,
  },
});
