import { Pressable, StyleSheet, View } from 'react-native'
import { useTranslation } from 'react-i18next'
import { useCooldown } from '@/api/useCooldown'
import { useUploadsPaused } from '@/api/rateLimits'
import { resumeRateLimitedUploads } from '@/services/storage'
import { AppText } from './AppText'
import { colors } from './colors'
import { formatRateLimitMessage } from './rateLimitMessage'

export function UploadRateLimitAlert() {
  const { t } = useTranslation()
  const paused = useUploadsPaused()
  const { retryAt, isBlocked } = useCooldown('upload')
  if (!paused) return null
  return (
    <View style={styles.container} accessibilityRole="alert">
      <AppText variant="bodyBold">{t('rateLimits.uploadsPausedShort')}</AppText>
      <AppText>{t('rateLimits.uploadsPaused')}</AppText>
      {/* With a Retry-After, the upload manager resumes uploads on its own. */}
      {isBlocked ? (
        <AppText>{formatRateLimitMessage(t, retryAt ?? null)}</AppText>
      ) : (
        <Pressable
          onPress={resumeRateLimitedUploads}
          accessibilityRole="button"
        >
          <AppText color={colors.primary}>
            {t('rateLimits.resumeUploads')}
          </AppText>
        </Pressable>
      )}
    </View>
  )
}

const styles = StyleSheet.create({
  container: {
    alignSelf: 'stretch',
    backgroundColor: colors.infoSurface,
    borderColor: colors.infoBorder,
    borderWidth: 1,
    borderRadius: 8,
    margin: 12,
    padding: 12,
    gap: 8,
  },
})
