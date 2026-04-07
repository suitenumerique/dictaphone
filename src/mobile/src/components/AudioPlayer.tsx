import React, { useRef, useState } from 'react';
import {
  GestureResponderEvent,
  PanResponder,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Lucide } from '@react-native-vector-icons/lucide';

export type AudioPlayerViewState = {
  durationMs: number;
  isLoading: boolean;
  isPaused: boolean;
  isPlaying: boolean;
  positionMs: number;
};

type AudioPlayerProps = {
  onSeek: (positionMs: number) => Promise<void> | void;
  onSetSpeed: (speed: number) => Promise<void> | void;
  onTogglePlay: () => Promise<void> | void;
  playbackSpeed: number;
  state: AudioPlayerViewState;
};

const msToTimestamp = (timeMs: number) => {
  const totalSeconds = Math.max(0, Math.floor(timeMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
};

const SPEED_OPTIONS = [1, 1.5, 2] as const;

export const AudioPlayer = ({ onSeek, onSetSpeed, onTogglePlay, playbackSpeed, state }: AudioPlayerProps) => {
  const [isSeeking, setIsSeeking] = useState(false);
  const [seekPreviewMs, setSeekPreviewMs] = useState(0);
  const [trackWidth, setTrackWidth] = useState(1);

  const displayedPositionMs = isSeeking ? seekPreviewMs : state.positionMs;
  const progressRatio = state.durationMs > 0
    ? Math.min(displayedPositionMs / state.durationMs, 1)
    : 0;


  const positionFromX = (x: number) => {
    const ratio = Math.max(0, Math.min(x / trackWidth, 1));
    return Math.floor(ratio * state.durationMs);
  };

  const handleTrackPress = async (event: GestureResponderEvent) => {
    const nextPosition = positionFromX(event.nativeEvent.locationX);
    await onSeek(nextPosition);
  };

  const seekTo = async (positionMs: number) => {
    const clamped = Math.max(0, Math.min(positionMs, state.durationMs));
    await onSeek(clamped);
  };

  const handleRestart = async () => {
    await seekTo(0);
  };

  const handleBack10 = async () => {
    await seekTo(state.positionMs - 10000);
  };

  const handleForward10 = async () => {
    await seekTo(state.positionMs + 10000);
  };

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: event => {
        const nextPosition = positionFromX(event.nativeEvent.locationX);
        setIsSeeking(true);
        setSeekPreviewMs(nextPosition);
      },
      onPanResponderMove: event => {
        const nextPosition = positionFromX(event.nativeEvent.locationX);
        setSeekPreviewMs(nextPosition);
      },
      onPanResponderRelease: async event => {
        const nextPosition = positionFromX(event.nativeEvent.locationX);
        await onSeek(nextPosition);
        setIsSeeking(false);
      },
      onPanResponderTerminate: () => {
        setIsSeeking(false);
      },
    }),
  ).current;

  return (
    <View style={styles.container}>
      <View style={styles.transportRow}>
        <Pressable
          style={[styles.controlButton, state.isLoading && styles.buttonDisabled]}
          onPress={handleRestart}
          disabled={state.isLoading}
        >
          <Lucide name="rotate-ccw" size={16}/>
        </Pressable>

        <Pressable
          style={[styles.controlButton, state.isLoading && styles.buttonDisabled]}
          onPress={handleBack10}
          disabled={state.isLoading}
        >
          <Text style={styles.controlButtonText}>-10s</Text>
        </Pressable>

        <Pressable
          style={[styles.playButton, state.isLoading && styles.buttonDisabled]}
          onPress={onTogglePlay}
          disabled={state.isLoading}
        >
          <Lucide name={state.isPlaying ? 'pause' : 'play'}/>
        </Pressable>

        <Pressable
          style={[styles.controlButton, state.isLoading && styles.buttonDisabled]}
          onPress={handleForward10}
          disabled={state.isLoading}
        >
          <Text style={styles.controlButtonText}>+10s</Text>
        </Pressable>
      </View>

      <View style={styles.speedRow}>
        {SPEED_OPTIONS.map(speed => (
          <Pressable
            key={speed}
            style={[
              styles.speedButton,
              playbackSpeed === speed && styles.speedButtonActive,
              state.isLoading && styles.buttonDisabled,
            ]}
            onPress={() => onSetSpeed(speed)}
            disabled={state.isLoading}
          >
            <Text style={[styles.speedButtonText, playbackSpeed === speed && styles.speedButtonTextActive]}>
              {speed}x
            </Text>
          </Pressable>
        ))}
      </View>

      <View
        style={styles.sliderArea}
        onLayout={event => setTrackWidth(Math.max(1, event.nativeEvent.layout.width))}
      >
        <Pressable style={styles.sliderTouchTarget} onPress={handleTrackPress}>
          <View style={styles.sliderTrack}>
            <View style={[styles.sliderProgress, { width: `${progressRatio * 100}%` }]} />
          </View>
        </Pressable>

        <View
          style={[
            styles.thumb,
            { left: Math.max(0, progressRatio * trackWidth - 9) },
          ]}
          {...panResponder.panHandlers}
        />
      </View>

      <View style={styles.timeRow}>
        <Text style={styles.timeText}>{msToTimestamp(displayedPositionMs)}</Text>
        <Text style={styles.timeText}>{msToTimestamp(state.durationMs)}</Text>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    gap: 12,
    width: '100%',
  },
  transportRow: {
    flexDirection: 'row',
    gap: 10,
    alignItems: 'center',
  },
  playButton: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#D1D5DB',
    paddingHorizontal: 18,
    paddingVertical: 10,
  },
  controlButton: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#D1D5DB',
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  controlButtonText: {
    color: '#111827',
    fontSize: 13,
    fontWeight: '600',
  },
  speedRow: {
    flexDirection: 'row',
    gap: 8,
  },
  speedButton: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#D1D5DB',
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  speedButtonActive: {
    borderColor: '#2563EB',
    backgroundColor: '#DBEAFE',
  },
  speedButtonText: {
    color: '#374151',
    fontSize: 13,
    fontWeight: '600',
  },
  speedButtonTextActive: {
    color: '#1D4ED8',
  },
  buttonDisabled: {
    opacity: 0.55,
  },
  sliderArea: {
    width: '100%',
    justifyContent: 'center',
    height: 30,
  },
  sliderTouchTarget: {
    width: '100%',
    paddingVertical: 8,
  },
  sliderTrack: {
    height: 6,
    backgroundColor: '#E5E7EB',
    borderRadius: 999,
    overflow: 'hidden',
  },
  sliderProgress: {
    height: '100%',
    backgroundColor: '#2563EB',
    borderRadius: 999,
  },
  thumb: {
    position: 'absolute',
    width: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: '#2563EB',
    borderWidth: 3,
    borderColor: '#FFFFFF',
    shadowColor: '#111827',
    shadowOpacity: 0.2,
    shadowRadius: 5,
    shadowOffset: { width: 0, height: 1 },
    elevation: 3,
  },
  timeRow: {
    width: '100%',
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  timeText: {
    fontSize: 13,
    color: '#6B7280',
    fontVariant: ['tabular-nums'],
  },
});
