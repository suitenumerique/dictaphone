import { useMemo } from 'react'
import { ApiFileItem } from '@/features/files/api/types'
import { getMainAiJobs } from '@/features/ai-jobs/utils/getMainAiJobs'
import { Duration, intervalToDuration } from 'date-fns'
import { useTranslation } from 'react-i18next'
import { ApiAiJob } from '@/features/ai-jobs/api/types'

export function useFormattedProcessingDuration(
  file: ApiFileItem | ApiAiJob | null
) {
  const { t } = useTranslation(['recordings', 'shared'])

  const expectedIn =
    file === null
      ? null
      : file.type === 'audio_recording'
        ? (getMainAiJobs(file.ai_jobs).lastAiJobTranscript
            ?.processing_expected_end_at ?? null)
        : (file.processing_expected_end_at ?? null)
  const processingIntervalRemaining = useMemo<Duration | null>(() => {
    if (expectedIn === null) return null
    const duration = intervalToDuration({ start: new Date(), end: expectedIn })
    if ((duration.hours ?? 0) > 0)
      return { hours: duration.hours, minutes: duration.minutes }
    if ((duration.minutes ?? 0) > 0)
      return { minutes: Math.max(duration.minutes!, 2) }
    return { minutes: 1 }
  }, [expectedIn])

  return useMemo(() => {
    if (processingIntervalRemaining === null) return null
    return t('shared:utils.durationLong', {
      duration: processingIntervalRemaining,
    })
  }, [processingIntervalRemaining, t])
}
