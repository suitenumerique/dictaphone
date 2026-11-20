import { renderToStaticMarkup } from 'react-dom/server'
import { expect, it, vi } from 'vitest'
import { AudioPlayer } from './AudioPlayer'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

it('renders the estimated duration without exposing an audio source to the browser', () => {
  const markup = renderToStaticMarkup(
    <AudioPlayer
      src="/media/recording-playback.ogg"
      downloadSrc="/media/recording.ogg"
      title="Recording"
      durationSecondsEstimate={95}
    />
  )

  expect(markup).toContain('<audio preload="none"></audio>')
  expect(markup).toContain('-1:35')
})
