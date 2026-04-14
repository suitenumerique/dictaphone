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
} from '@gouvfr-lasuite/ui-kit'
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
    },
    ref
  ) => {
    const { t } = useTranslation('recordings')
    const audioRef = useRef<HTMLAudioElement>(null)
    const [isPlaying, setIsPlaying] = useState(false)
    const [currentTime, setCurrentTime] = useState(0)
    const [duration, setDuration] = useState(0)

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
        }
      }

      document.addEventListener('keydown', handleKeyDown)
      return () => {
        document.removeEventListener('keydown', handleKeyDown)
      }
    }, [togglePlayPause, handleRewind10Seconds, handleForward10Seconds])

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
              aria-label={isPlaying ? t('player:pause') : t('player:play')}
              size={'nano'}
            />
            <div className="audio-player__separator" />
            <Button
              variant="tertiary"
              color="neutral"
              onClick={handleRewind10Seconds}
              className="audio-player__btn"
              icon={<FastBackward />}
              aria-label={t('player:rewind')}
              size={'nano'}
            />
            <Button
              variant="tertiary"
              color="neutral"
              onClick={handleForward10Seconds}
              className="audio-player__btn"
              icon={<FastForward />}
              aria-label={t('player:forward')}
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
              aria-label={t('player:progressControl')}
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
              aria-label={t('player:download')}
              size={'nano'}
            />
          </div>
        </div>
      </div>
    )
  }
)

AudioPlayer.displayName = 'AudioPlayer'
