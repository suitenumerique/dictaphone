import { Pressable, View } from 'react-native'
import { useTranslation } from 'react-i18next'
import { useCooldown } from '@/api/useCooldown'
import { useUploadsPaused } from '@/api/rateLimits'
import { resumeRateLimitedUploads } from '@/services/storage'
import { AppText } from './AppText'
import { formatRateLimitMessage } from './rateLimitMessage'

export function UploadRateLimitAlert() {
  const { t } = useTranslation()
  const paused = useUploadsPaused()
  const { retryAt, isBlocked } = useCooldown('upload')
  if (!paused) return null
  return (
    <View style={{ padding: 12, gap: 8 }} accessibilityRole="alert">
      <AppText>{t('rateLimits.uploadsPaused')}</AppText>
      {isBlocked && (
        <AppText>{formatRateLimitMessage(t, retryAt ?? null)}</AppText>
      )}
      <Pressable
        disabled={isBlocked}
        onPress={resumeRateLimitedUploads}
        accessibilityRole="button"
        accessibilityState={{ disabled: isBlocked }}
      >
        <AppText>{t('rateLimits.resumeUploads')}</AppText>
      </Pressable>
    </View>
  )
}
