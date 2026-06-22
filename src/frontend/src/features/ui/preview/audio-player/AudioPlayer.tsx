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
import { Button } from '@gouvfr-lasuite/cunningham-react'
import {
  Download,
  FastBackward,
  FastForward,
  Pause,
  Play,
} from '@gouvfr-lasuite/ui-kit/icons'
import { useTranslation } from 'react-i18next'

export interface AudioPlayerHandle {
  seekTo: (seconds: number) => void
}

interface AudioPlayerProps {
  src: string
  title: string
  extraTitle?: React.ReactElement
  className?: string
  autoPlay?: boolean
  onPlay?: () => void
  onPause?: () => void
  onEnded?: () => void
  onTimeUpdate?: (currentTime: number) => void
  durationSecondsEstimate?: number
}

const formatTime = (time: number): string => {
  const safeTime = Number.isFinite(time) ? Math.max(0, time) : 0
  const minutes = Math.floor(safeTime / 60)
  const seconds = Math.floor(safeTime % 60)
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

export const AudioPlayer = forwardRef<AudioPlayerHandle, AudioPlayerProps>(
  (
    {
      src,
      title,
      className,
      autoPlay = false,
      onPlay,
      onPause,
      onEnded,
      onTimeUpdate,
      durationSecondsEstimate,
    },
    ref
  ) => {
    const { t } = useTranslation('recordings')
    const audioRef = useRef<HTMLAudioElement>(null)
    const [isPlaying, setIsPlaying] = useState(false)
    const [currentTime, setCurrentTime] = useState(0)
    const [duration, setDuration] = useState(durationSecondsEstimate ?? 0)
    const [playbackRate, setPlaybackRate] = useState(1)

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

    // Audio event handlers
    const handleLoadedMetadata = useCallback(() => {
      if (audioRef.current) {
        setDuration(audioRef.current.duration)
        audioRef.current.playbackRate = playbackRate
      }
    }, [playbackRate])

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

    const handlePlaybackRateChange = useCallback(() => {
      setPlaybackRate((oldRate) => {
        const rate = oldRate === 1 ? 1.5 : oldRate === 1.5 ? 2 : 1
        if (audioRef.current) {
          audioRef.current.playbackRate = rate
        }
        return rate
      })
    }, [])

    const handleDownload = useCallback(() => {
      let filename = title.trim()
      try {
        const parsedUrl = new URL(src, window.location.href)
        const fileFromPath = decodeURIComponent(
          parsedUrl.pathname.split('/').pop() || ''
        )
        if (fileFromPath) {
          filename = `${filename}.${fileFromPath.split('.')?.at(-1)}`
        }
      } catch {
        // Ignore malformed URL and keep default filename.
      }

      const link = document.createElement('a')
      link.href = src
      link.download = filename
      link.rel = 'noopener noreferrer'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    }, [src, title])

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

    useEffect(() => {
      const handleKeyDown = (event: KeyboardEvent) => {
        switch (event.code) {
          case 'Space':
            event.preventDefault()
            togglePlayPause()
            break
          case 'ArrowLeft':
            event.preventDefault()
            handleRewind10Seconds()
            break
          case 'ArrowRight':
            event.preventDefault()
            handleForward10Seconds()
            break
          case 'KeyS':
            event.preventDefault()
            handlePlaybackRateChange()
            break
        }
      }

      document.addEventListener('keydown', handleKeyDown)
      return () => {
        document.removeEventListener('keydown', handleKeyDown)
      }
    }, [
      togglePlayPause,
      handleRewind10Seconds,
      handleForward10Seconds,
      handlePlaybackRateChange,
    ])

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
        audioRef.current.playbackRate = 1

        // Reset state
        setIsPlaying(false)
        setCurrentTime(0)
        setDuration(0)
        setPlaybackRate(1)
      }
    }, [src])

    const progressPercentage = duration > 0 ? (currentTime / duration) * 100 : 0
    const remainingTime = duration > 0 ? Math.max(duration - currentTime, 0) : 0

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
          <div className="audio-player__controls">
            <Button
              variant="tertiary"
              color="neutral"
              onClick={togglePlayPause}
              className="audio-player__btn"
              icon={isPlaying ? <Pause /> : <Play />}
              aria-label={isPlaying ? t('player.pause') : t('player.play')}
              size={'nano'}
            />
            <Button
              variant="tertiary"
              color="neutral"
              onClick={() => handlePlaybackRateChange()}
              className="audio-player__btn"
              icon={
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  height="24px"
                  viewBox="0 -960 960 960"
                  width="24px"
                  fill="currentColor"
                >
                  {/* No icons in the UI kit yet, and couldn't make material icons work here, so went for svg.*/}
                  {playbackRate === 1 && (
                    <path d="M240-280v-320h-80v-80h160v400h-80Zm174 0 126-212-114-188h94l66 110 68-110h92L634-492l126 212h-94l-80-134-80 134h-92Z" />
                  )}
                  {playbackRate === 1.5 && (
                    <path d="M240-280v-80h80v80h-80Zm-120 0v-320H40v-80h160v400h-80Zm500 0 120-200-120-200h80l80 133 80-133h80L820-480l120 200h-80l-80-133-80 133h-80Zm-260 0v-80h140v-80H360v-240h220v80H440v80h60q33 0 56.5 23.5T580-440v80q0 33-23.5 56.5T500-280H360Z" />
                  )}
                  {playbackRate === 2 && (
                    <path d="M200-280v-160q0-33 23.5-56.5T280-520h80v-80H200v-80h160q33 0 56.5 23.5T440-600v80q0 33-23.5 56.5T360-440h-80v80h160v80H200Zm280 0 120-200-120-200h80l80 133 80-133h80L680-480l120 200h-80l-80-133-80 133h-80Z" />
                  )}
                </svg>
              }
              aria-label={
                playbackRate === 1
                  ? t('player.speed15')
                  : playbackRate === 1.5
                    ? t('player.speed2')
                    : t('player.speed1')
              }
              size={'nano'}
            />
            <div className="audio-player__separator" />
            <Button
              variant="tertiary"
              color="neutral"
              onClick={handleRewind10Seconds}
              className="audio-player__btn"
              icon={<FastBackward />}
              aria-label={t('player.rewind')}
              size={'nano'}
            />
            <Button
              variant="tertiary"
              color="neutral"
              onClick={handleForward10Seconds}
              className="audio-player__btn"
              icon={<FastForward />}
              aria-label={t('player.forward')}
              size={'nano'}
            />
            <div className="audio-player__separator" />
            <div className="audio-player__time">{formatTime(currentTime)}</div>
            <input
              type="range"
              min={0}
              max={duration || 0}
              value={currentTime}
              step={0.01}
              onChange={handleSeek}
              className="audio-player__timeline"
              aria-label={t('player.progressControl')}
              style={
                {
                  '--progress-percentage': `${progressPercentage}%`,
                } as React.CSSProperties
              }
            />
            <div className="audio-player__time audio-player__time--remaining">
              -{formatTime(remainingTime)}
            </div>
            <div className="audio-player__separator" />
            <Button
              variant="tertiary"
              color="neutral"
              onClick={handleDownload}
              className="audio-player__btn"
              icon={<Download />}
              aria-label={t('player.download')}
              size={'nano'}
            />
          </div>
        </div>
      </div>
    )
  }
)

AudioPlayer.displayName = 'AudioPlayer'
