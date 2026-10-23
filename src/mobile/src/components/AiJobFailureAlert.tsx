import { Linking, Pressable, StyleSheet, View } from 'react-native'
import { useTranslation } from 'react-i18next'
import { intervalToDuration } from 'date-fns'
import type { ApiAiJob } from '@/features/ai-jobs/api/types'
import { getFailureMessageKey } from '@/features/ai-jobs/utils/failurePresentation'
import { useConfigStore } from '@/services/configStore'
import { AppText } from './AppText'
import { colors } from './colors'

export function AiJobFailureAlert({ job }: { job: ApiAiJob | null }) {
  const { t } = useTranslation()
  const config = useConfigStore((state) => state.config)
  const key = getFailureMessageKey(job)
  if (!key) return null
  const tooLong = job?.failure_reason === 'AUDIO_TOO_LONG'
  const quota = job?.failure_reason === 'RATE_LIMIT_TRANSCRIPTION_EXCEEDED'
  const hours = config?.rate_limit_ai_transcription_audio_hours_per_24h
  return (
    <View
      accessibilityRole="alert"
      style={[styles.container, quota && styles.warning]}
    >
      <AppText variant="bodyBold">{t(key)}</AppText>
      {tooLong && (
        <>
          {config && (
            <AppText>
              {t('recordings.failures.tooLongDescription', {
                duration: t('shared.utils.duration', {
                  duration: intervalToDuration({
                    start: 0,
                    end: config.audio_recording.max_duration_seconds * 1000,
                  }),
                }),
              })}
            </AppText>
          )}
          <Pressable
            accessibilityRole="link"
            onPress={() =>
              void Linking.openURL(t('recordings.failures.tooLongFaqUrl'))
            }
          >
            <AppText>{t('recordings.failures.faq')}</AppText>
          </Pressable>
        </>
      )}
      {quota && (
        <AppText>
          {hours == null
            ? t('recordings.failures.quotaWithoutLimit')
            : t('recordings.failures.quotaDescription', { hours })}
        </AppText>
      )}
    </View>
  )
}

const styles = StyleSheet.create({
  container: {
    gap: 8,
    paddingVertical: 12,
  },
  warning: {
    alignSelf: 'stretch',
    backgroundColor: colors.warningSurface,
    borderColor: colors.warningBorder,
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
  },
})
