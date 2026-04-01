'use client'

import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react'
import { clsx } from 'clsx'
import { ProgressBar } from '../components/duration-bar/DurationBar'
import { PreviewControls } from '../components/controls/PreviewControls'

export interface AudioPlayerHandle {
  seekTo: (seconds: number) => void
}

interface AudioPlayerProps {
  src: string
  title?: string
  extraTitle?: React.ReactElement
  className?: string
  autoPlay?: boolean
  onPlay?: () => void
  onPause?: () => void
  onEnded?: () => void
  onTimeUpdate?: (currentTime: number) => void
}

export const AudioPlayer = forwardRef<AudioPlayerHandle, AudioPlayerProps>(
  (
    {
      src,
      title = 'Audio Track',
      className,
      autoPlay = false,
      onPlay,
      onPause,
      onEnded,
      onTimeUpdate,
      extraTitle,
    },
    ref
  ) => {
    const audioRef = useRef<HTMLAudioElement>(null)
    const [isPlaying, setIsPlaying] = useState(false)
    const [currentTime, setCurrentTime] = useState(0)
    const [duration, setDuration] = useState(0)
    const [volume, setVolume] = useState(1)
    const [isMuted, setIsMuted] = useState(false)

    const seekTo = useCallback(
      (seconds: number) => {
        if (!audioRef.current) return

        const maxTime =
          Number.isFinite(duration) && duration > 0
            ? duration
            : audioRef.current.duration || 0

        const nextTime = Math.max(0, Math.min(seconds, maxTime))
        audioRef.current.currentTime = nextTime
        setCurrentTime(nextTime)
        onTimeUpdate?.(nextTime)
      },
      [duration, onTimeUpdate]
    )

    useImperativeHandle(
      ref,
      () => ({
        seekTo,
      }),
      [seekTo]
    )

    // Handle play/pause
    const togglePlayPause = useCallback(() => {
      if (audioRef.current) {
        if (isPlaying) {
          audioRef.current.pause()
        } else {
          audioRef.current.play()
        }
      }
    }, [isPlaying])

    // Handle volume change
    const handleVolumeChange = useCallback((newVolume: number) => {
      setVolume(newVolume)
      if (audioRef.current) {
        audioRef.current.volume = newVolume
      }
    }, [])

    // Handle mute/unmute
    const toggleMute = useCallback(() => {
      if (audioRef.current) {
        if (isMuted) {
          audioRef.current.volume = volume
          setIsMuted(false)
        } else {
          audioRef.current.volume = 0
          setIsMuted(true)
        }
      }
    }, [isMuted, volume])

    // Handle seek
    const handleSeek = useCallback(
      (e: React.ChangeEvent<HTMLInputElement>) => {
        const newTime = parseFloat(e.target.value)
        setCurrentTime(newTime)
        onTimeUpdate?.(newTime)
        if (audioRef.current) {
          audioRef.current.currentTime = newTime
        }
      },
      [onTimeUpdate]
    )

    // Audio event handlers
    const handleLoadedMetadata = useCallback(() => {
      if (audioRef.current) {
        setDuration(audioRef.current.duration)
      }
    }, [])

    const handleTimeUpdate = useCallback(() => {
      if (audioRef.current) {
        setCurrentTime(audioRef.current.currentTime)
        onTimeUpdate?.(audioRef.current.currentTime)
      }
    }, [onTimeUpdate])

    const handlePlay = useCallback(() => {
      setIsPlaying(true)
      onPlay?.()
    }, [onPlay])

    const handlePause = useCallback(() => {
      setIsPlaying(false)
      onPause?.()
    }, [onPause])

    const handleEnded = useCallback(() => {
      setIsPlaying(false)
      setCurrentTime(0)
      onEnded?.()
    }, [onEnded])

    const handleRewind10Seconds = useCallback(() => {
      if (audioRef.current) {
        const nextTime = Math.max(0, currentTime - 10)
        audioRef.current.currentTime = nextTime
        setCurrentTime(nextTime)
        onTimeUpdate?.(nextTime)
      }
    }, [currentTime, onTimeUpdate])

    const handleForward10Seconds = useCallback(() => {
      if (audioRef.current) {
        const nextTime = Math.min(duration, currentTime + 10)
        audioRef.current.currentTime = nextTime
        setCurrentTime(nextTime)
        onTimeUpdate?.(nextTime)
      }
    }, [currentTime, duration, onTimeUpdate])

    // Auto-play effect
    useEffect(() => {
      if (autoPlay && audioRef.current) {
        audioRef.current.play().catch(console.error)
      }
    }, [autoPlay, src])

    // Reset player state when source changes
    useEffect(() => {
      if (audioRef.current) {
        // Reset audio element
        audioRef.current.currentTime = 0

        // Reset state
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setIsPlaying(false)
        setCurrentTime(0)
        setDuration(0)
      }
    }, [src])

    useEffect(() => {
      if (audioRef.current) {
        audioRef.current.volume = volume
      }
    }, [volume])

    return (
      <div className={clsx('audio-player', className)}>
        {/* Hidden audio element */}
        {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
        <audio
          ref={audioRef}
          src={src}
          onCanPlay={handleLoadedMetadata}
          onLoadedMetadata={handleLoadedMetadata}
          onTimeUpdate={handleTimeUpdate}
          onPlay={handlePlay}
          onPause={handlePause}
          onEnded={handleEnded}
        />

        {/* Player interface */}
        <div className="audio-player__container">
          {/* Track info */}
          <div className="audio-player__info">
            <div className="audio-player__title">{title}</div>
            {extraTitle}
          </div>

          <ProgressBar
            duration={duration}
            currentTime={currentTime}
            handleSeek={handleSeek}
          />

          <PreviewControls
            togglePlay={togglePlayPause}
            isPlaying={isPlaying}
            rewind10Seconds={handleRewind10Seconds}
            forward10Seconds={handleForward10Seconds}
            volume={volume}
            isMuted={isMuted}
            toggleMute={toggleMute}
            handleVolumeChange={handleVolumeChange}
            toggleFullscreen={() => {}}
            isFullscreen={false}
          />
        </div>
      </div>
    )
  }
)

AudioPlayer.displayName = 'AudioPlayer'
