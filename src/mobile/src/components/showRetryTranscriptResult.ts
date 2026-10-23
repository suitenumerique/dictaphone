import { Alert } from 'react-native'
import type { TFunction } from 'i18next'
import type { ApiAiJob } from '@/features/ai-jobs/api/types'
import { getFailureMessageKey } from '@/features/ai-jobs/utils/failurePresentation'
import { useConfigStore } from '@/services/configStore'

export function showRetryTranscriptResult(t: TFunction, job: ApiAiJob) {
  const failureKey = getFailureMessageKey(job)
  if (failureKey === 'recordings.failures.quota') {
    const hours =
      useConfigStore.getState().config
        ?.rate_limit_ai_transcription_audio_hours_per_24h
    Alert.alert(
      t('recordings.failures.quotaRetryTitle'),
      hours == null
        ? t('recordings.failures.quotaWithoutLimit')
        : t('recordings.failures.quotaDescription', { hours })
    )
    return
  }
  Alert.alert(failureKey ? t(failureKey) : t('recordings.menu.retrySuccess'))
}
