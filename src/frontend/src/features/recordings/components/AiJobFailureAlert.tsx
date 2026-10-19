import { useTranslation } from 'react-i18next'
import { intervalToDuration } from 'date-fns'
import { useConfig } from '@/api/useConfig'
import type { ApiAiJob } from '@/features/ai-jobs/api/types'
import { getFailureMessageKey } from '@/features/ai-jobs/utils/failurePresentation'

export function AiJobFailureAlert({ job }: { job: ApiAiJob | null }) {
  const { t } = useTranslation(['recordings', 'shared'])
  const { data: config } = useConfig()
  const key = getFailureMessageKey(job)
  if (!key) return null
  const tooLong = job?.failure_reason === 'AUDIO_TOO_LONG'
  const quota = job?.failure_reason === 'RATE_LIMIT_TRANSCRIPTION_EXCEEDED'
  const hours = config?.rate_limit_ai_transcription_audio_hours_per_24h
  return (
    <div className="limit-alert" role="alert">
      <strong>{t(key)}</strong>
      {tooLong && (
        <>
          {config?.audio_recording.max_duration_seconds != null && (
            <p>
              {t('failures.tooLongDescription', {
                duration: t('shared:utils.duration', {
                  duration: intervalToDuration({
                    start: 0,
                    end: config.audio_recording.max_duration_seconds * 1000,
                  }),
                }),
              })}
            </p>
          )}
          <a
            href={t('failures.tooLongFaqUrl')}
            target="_blank"
            rel="noopener noreferrer"
          >
            {t('failures.faq')}
          </a>
        </>
      )}
      {quota && (
        <p>
          {hours == null
            ? t('failures.quotaWithoutLimit')
            : t('failures.quotaDescription', { hours })}
        </p>
      )}
    </div>
  )
}
