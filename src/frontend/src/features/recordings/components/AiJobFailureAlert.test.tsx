import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { createInstance } from 'i18next'
import { I18nextProvider } from 'react-i18next'
import enRecordings from '@/locales/en-US/recordings.json'
import enShared from '@/locales/en-US/shared.json'
import frRecordings from '@/locales/fr-FR/recordings.json'
import frShared from '@/locales/fr-FR/shared.json'
import type { ApiAiJob } from '@/features/ai-jobs/api/types'
import { AiJobFailureAlert } from './AiJobFailureAlert'

vi.mock('@/api/useConfig', () => ({
  useConfig: () => ({
    data: {
      audio_recording: { max_duration_seconds: 3600 },
      rate_limit_ai_transcription_audio_hours_per_24h: 12,
    },
  }),
}))

const job = (
  failure_reason: string,
  status: ApiAiJob['status'] = 'failed'
): ApiAiJob => ({
  id: 'job',
  type: 'transcript',
  status,
  failure_reason,
  created_at: '',
  updated_at: '',
  language: 'fr',
  docs_app_id: null,
  processing_expected_end_at: null,
})

async function render(failure: ApiAiJob, language = 'en-US') {
  const i18n = createInstance()
  await i18n.init({
    lng: language,
    defaultNS: 'recordings',
    interpolation: { escapeValue: false },
    resources: {
      'en-US': { recordings: enRecordings, shared: enShared },
      'fr-FR': { recordings: frRecordings, shared: frShared },
    },
  })
  return renderToStaticMarkup(
    <I18nextProvider i18n={i18n}>
      <AiJobFailureAlert job={failure} />
    </I18nextProvider>
  )
}

describe('AI failure alerts', () => {
  it('shows the long-audio explanation and a safe FAQ link', async () => {
    const markup = await render(job('AUDIO_TOO_LONG'))
    expect(markup).toContain('role="alert"')
    expect(markup).toContain(enRecordings.failures.tooLong)
    expect(markup).toContain(
      'href="' + enRecordings.failures.tooLongFaqUrl + '"'
    )
    expect(markup).toContain('rel="noopener noreferrer"')
  })
  it.each(['en-US', 'fr-FR'])(
    'uses the configured rolling quota in %s',
    async (language) => {
      const markup = await render(
        job('RATE_LIMIT_TRANSCRIPTION_EXCEEDED'),
        language
      )
      expect(markup).toContain('12')
      expect(markup).toContain(
        language === 'fr-FR'
          ? 'période glissante de 24 heures'
          : 'rolling 24-hour period'
      )
      expect(markup).not.toContain('href=')
    }
  )
  it('falls back for new reasons and renders nothing for non-failed jobs', async () => {
    expect(await render(job('NEW_REASON'))).toContain(
      enRecordings.transcript.status.failed
    )
    expect(await render(job('AUDIO_TOO_LONG', 'pending'))).toBe('')
  })
})
