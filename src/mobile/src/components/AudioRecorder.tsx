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
  PermissionsAndroid,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useTranslation } from 'react-i18next';
import Sound from 'react-native-nitro-sound';
import { Lucide } from '@react-native-vector-icons/lucide';

type RecordingResult = {
  createdAt: string;
  duration: number;
  filePath: string;
};

type AudioRecorderProps = {
  onRecordingComplete?: (recording: RecordingResult) => void;
};

export const AudioRecorder = ({ onRecordingComplete }: AudioRecorderProps) => {
  const { t } = useTranslation();
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [recordTimeLabel, setRecordTimeLabel] = useState('00:00');
  const durationMsRef = useRef(0);
  const pulse = useRef(new Animated.Value(1)).current;

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

  useEffect(() => {
    return () => {
      Sound.removeRecordBackListener();
    };
  }, []);

  const onStartRecord = useCallback(async () => {
    if (Platform.OS === 'android') {
      try {
        const granted = await PermissionsAndroid.request(
          PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
          {
            title: t('home.microphonePermissionTitle'),
            message: t('home.microphonePermissionMessage'),
            buttonNeutral: t('home.permissionAskLater'),
            buttonNegative: t('home.permissionCancel'),
            buttonPositive: t('home.permissionOk'),
          },
        );

        if (granted === PermissionsAndroid.RESULTS.GRANTED) {
          console.log('Recording permission granted');
        } else {
          console.log('Recording permission denied');
          return;
        }
      } catch (err) {
        console.warn(err);
        return;
      }
    }

    setIsLoading(true);
    try {
      await Sound.startRecorder();
      durationMsRef.current = 0;
      setRecordTimeLabel('00:00');
      Sound.addRecordBackListener(e => {
        durationMsRef.current = Math.floor(e.currentPosition);
        setRecordTimeLabel(Sound.mmssss(durationMsRef.current));
      });
      setIsRecording(true);
      setIsPaused(false);
    } catch (error) {
      console.error('Failed to start recording:', error);
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  const onPauseRecord = useCallback(async () => {
    setIsLoading(true);
    try {
      await Sound.pauseRecorder();
      setIsPaused(true);
    } catch (error) {
      console.error('Failed to pause recording:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const onResumeRecord = useCallback(async () => {
    setIsLoading(true);
    try {
      await Sound.resumeRecorder();
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
      const filePath = await Sound.stopRecorder();
      Sound.removeRecordBackListener();
      setIsRecording(false);
      setIsPaused(false);
      onRecordingComplete?.({
        createdAt: new Date().toISOString(),
        duration: durationMsRef.current,
        filePath,
      });
      durationMsRef.current = 0;
      setRecordTimeLabel('00:00');
    } catch (error) {
      console.error('Failed to stop recording:', error);
    } finally {
      setIsLoading(false);
    }
  }, [onRecordingComplete]);

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
            await Sound.stopRecorder();
            Sound.removeRecordBackListener();
            setIsRecording(false);
            setIsPaused(false);
            setRecordTimeLabel('00:00');
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
          <Lucide name="save" size={36} /><Text>{t("home.save")}</Text>
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
