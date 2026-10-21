import { Pressable, StyleSheet, View } from 'react-native'
import { useTranslation } from 'react-i18next'
import { isRateLimitError } from '@/api/rateLimits'
import { useCooldown } from '@/api/useCooldown'
import { AppText } from './AppText'
import { colors } from './colors'
import { formatRateLimitMessage } from './rateLimitMessage'

export function TranscriptErrorAlert({
  error,
  onRetry,
}: {
  error: unknown
  onRetry: () => void
}) {
  const { t } = useTranslation()
  const { isBlocked, retryAt } = useCooldown('aiResult')

  return (
    <View accessibilityRole="alert" style={styles.container}>
      <AppText variant="bodyBold">
        {isRateLimitError(error)
          ? t('rateLimits.title')
          : t('transcript.notAvailable')}
      </AppText>
      {isBlocked && (
        <AppText>{formatRateLimitMessage(t, retryAt ?? null)}</AppText>
      )}
      <Pressable
        disabled={isBlocked}
        onPress={onRetry}
        accessibilityRole="button"
        accessibilityState={{ disabled: isBlocked }}
      >
        <AppText color={isBlocked ? colors.neutralTertiary : colors.primary}>
          {t('rateLimits.retry')}
        </AppText>
      </Pressable>
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
    padding: 12,
    gap: 8,
  },
})
