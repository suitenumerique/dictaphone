import { Button } from '@gouvfr-lasuite/cunningham-react'
import { Icon } from '@gouvfr-lasuite/ui-kit'
import { VolumeBar } from '../volume-bar/VolumeBar'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'

export type PreviewControlsProps = {
  togglePlay: () => void
  isPlaying: boolean
  rewind10Seconds: () => void
  forward10Seconds: () => void
  volume: number
  isMuted: boolean
  toggleMute: () => void
  handleVolumeChange: (newVolume: number) => void
  toggleFullscreen: () => void
  isFullscreen: boolean
  showFullscreenBtn?: boolean
}

export const PreviewControls = ({
  togglePlay,
  isPlaying,
  rewind10Seconds,
  forward10Seconds,
  volume,
  isMuted,
  toggleMute,
  handleVolumeChange,
  toggleFullscreen,
  isFullscreen,
  showFullscreenBtn = false,
}: PreviewControlsProps) => {
  const { t } = useTranslation('recordings')
  // Keyboard controls
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Only handle keyboard events when video player is focused or when not in fullscreen
      if (isFullscreen) return

      switch (event.code) {
        case 'Space':
          event.preventDefault()
          togglePlay()
          break
        case 'ArrowLeft':
          event.preventDefault()
          rewind10Seconds()
          break
        case 'ArrowRight':
          event.preventDefault()
          forward10Seconds()
          break
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [togglePlay, rewind10Seconds, forward10Seconds, isFullscreen])
  return (
    <div className="suite-preview-controls">
      <Button
        variant="tertiary"
        color="neutral"
        onClick={togglePlay}
        className="suite-preview-controls__btn"
        icon={<Icon name={isPlaying ? 'pause' : 'play_arrow'} />}
        aria-label={isPlaying ? t('player:pause') : t('player:play')}
      />
      <VerticalSeparator />
      <Button
        variant="tertiary"
        color="neutral"
        onClick={rewind10Seconds}
        className="suite-preview-controls__btn"
        icon={<Icon name={'replay_10'} />}
        aria-label={t('player:rewind')}
      />
      <Button
        variant="tertiary"
        color="neutral"
        onClick={forward10Seconds}
        className="suite-preview-controls__btn"
        icon={<Icon name={'forward_10'} />}
        aria-label={t('player:forward')}
      />
      <VerticalSeparator />

      <VolumeBar
        volume={volume}
        isMuted={isMuted}
        toggleMute={toggleMute}
        handleVolumeChange={handleVolumeChange}
      />

      {showFullscreenBtn && (
        <>
          <VerticalSeparator />

          <Button
            variant="tertiary"
            color="neutral"
            onClick={toggleFullscreen}
            className="suite-preview-controls__btn"
            icon={
              <Icon name={isFullscreen ? 'fullscreen_exit' : 'fullscreen'} />
            }
          />
        </>
      )}
    </div>
  )
}

const VerticalSeparator = () => {
  return <div className="controls-vertical-separator" />
}
