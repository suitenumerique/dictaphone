import AudioPlayer from 'react-h5-audio-player'
import { useTranslation } from 'react-i18next'
import { ComponentProps, useMemo } from 'react'

export default function Player({ src }: { src: string }) {
  const { t } = useTranslation('recordings', { keyPrefix: 'player' })

  const ariaLabels = useMemo<
    ComponentProps<typeof AudioPlayer>['i18nAriaLabels']
  >(
    () => ({
      player: t('player'),
      progressControl: t('progressControl'),
      volumeControl: t('volumeControl'),
      play: t('play'),
      pause: t('pause'),
      rewind: t('rewind'),
      forward: t('forward'),
      previous: t('previous'),
      next: t('next'),
      loop: t('loop'),
      loopOff: t('loopOff'),
      volume: t('volume'),
      volumeMute: t('volumeMute'),
    }),
    [t]
  )
  return <AudioPlayer src={src} loop={false} i18nAriaLabels={ariaLabels} />
}
