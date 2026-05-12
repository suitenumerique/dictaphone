import React from 'react'
import { Pressable, StyleSheet, View } from 'react-native'
import { Lucide } from '@react-native-vector-icons/lucide'
import type { TFunction } from 'i18next'
// @ts-expect-error Icon
import RecordIcon from '@/assets/icons/record.svg'
import { AppText } from '@/components/AppText'
import { colors } from '@/components/colors'

type StartRecordingSectionProps = {
  onStartRecording: () => void
  t: TFunction
}

export function StartRecordingSection({
  onStartRecording,
  t,
}: StartRecordingSectionProps) {
  return (
    <View style={styles.startRecordingContainer}>
      <Pressable
        style={({ pressed }) => [
          styles.startRecordingButton,
          pressed && styles.startRecordingButtonPressed,
        ]}
        onPress={onStartRecording}
        accessibilityLabel={t('home.newRecording')}
        accessibilityRole="button"
      >
        <RecordIcon width={24} height={24} />
        <AppText variant="button" color={colors.errorSecondary}>
          {t('home.newRecording')}
        </AppText>
      </Pressable>

      <View style={styles.consentRow}>
        <AppText
          variant="muted"
          size="md"
          align="center"
          color={colors.neutralTertiary}
          style={styles.consentText}
        >
          <Lucide
            name="triangle-alert"
            color={colors.neutralTertiary}
            size={12}
          />{' '}
          {t('home.consentNotice')}
        </AppText>
      </View>
    </View>
  )
}

const styles = StyleSheet.create({
  startRecordingContainer: {
    width: '100%',
    marginBottom: 8,
    padding: 8,
    gap: 8,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    borderRadius: 12,
    backgroundColor: colors.backgroundBase,
    borderWidth: 1,
    borderColor: colors.surfacePrimary,
    boxShadow: [
      {
        blurRadius: 12,
        spreadDistance: 4,
        color: colors.backgroundNeutralTertiary,
        offsetX: 0,
        offsetY: 0,
      },
    ],
  },
  startRecordingButton: {
    backgroundColor: colors.backgroundErrorSecondary,
    borderRadius: 4,
    minHeight: 40,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 10,
    width: '100%',
  },
  startRecordingButtonPressed: {
    backgroundColor: colors.backgroundErrorSecondaryPressed,
  },
  consentRow: {},
  consentText: {
    flexShrink: 1,
  },
})
