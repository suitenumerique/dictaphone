import React, { useMemo, useState } from 'react'
import { Pressable, StyleSheet, View } from 'react-native'
import { Lucide } from '@react-native-vector-icons/lucide'
import type { TFunction } from 'i18next'
import Popover from 'react-native-popover-view'
// @ts-expect-error Icon
import RecordIcon from '@/assets/icons/record.svg'
import { AppText } from '@/components/AppText'
import { colors } from '@/components/colors'
import { TRANSCRIPTION_LANGUAGES } from '@/features/ai-jobs/constants'
import { useSettingsStore } from '@/services/storage'

type StartRecordingSectionProps = {
  onStartRecording: () => void
  t: TFunction
}

export function StartRecordingSection({
  onStartRecording,
  t,
}: StartRecordingSectionProps) {
  const [isPopoverVisible, setIsPopoverVisible] = useState(false)
  const newTranscriptionLanguage = useSettingsStore(
    (state) => state.newTranscriptionLanguage
  )
  const appLanguage = useSettingsStore((state) => state.settings.language)
  const setNewTranscriptionLanguage = useSettingsStore(
    (state) => state.setNewTranscriptionLanguage
  )

  const selectedTranscriptionLanguage =
    newTranscriptionLanguage ?? (appLanguage === 'en' ? 'en' : 'fr')

  const selectedLanguageLabel = useMemo(
    () =>
      t(
        `recordings.menu.retryModal.languageOptions.${selectedTranscriptionLanguage}`
      ),
    [selectedTranscriptionLanguage, t]
  )

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
      <View style={styles.consentRow}>
        <View style={styles.languageRow}>
          <AppText
            variant="muted"
            size="md"
            align="center"
            color={colors.neutralTertiary}
            style={styles.consentText}
          >
            {t('home.pickLanguage')}
          </AppText>
          <Popover
            isVisible={isPopoverVisible}
            arrowSize={{ width: 0, height: 0 }}
            popoverStyle={styles.popover}
            onRequestClose={() => setIsPopoverVisible(false)}
            from={
              <Pressable
                style={({ pressed }) => [
                  styles.languageButton,
                  pressed && styles.languageButtonPressed,
                ]}
                onPress={() => setIsPopoverVisible(true)}
                accessibilityRole="button"
                accessibilityLabel={t('home.pickLanguage')}
              >
                <AppText variant="muted" size="md" color={colors.textPrimary}>
                  {selectedLanguageLabel}
                </AppText>
                <Lucide
                  style={styles.languageButtonIcon}
                  name="chevrons-up-down"
                  size={15}
                  color={colors.neutralTertiary}
                />
              </Pressable>
            }
          >
            <View style={styles.popoverContent}>
              {TRANSCRIPTION_LANGUAGES.map((language) => {
                const isSelected = language === selectedTranscriptionLanguage

                return (
                  <Pressable
                    key={language}
                    style={({ pressed }) => [
                      styles.actionButton,
                      pressed && styles.actionButtonPressed,
                    ]}
                    onPress={() => {
                      setNewTranscriptionLanguage(language)
                      setIsPopoverVisible(false)
                    }}
                  >
                    <AppText variant="body">
                      {t(
                        `recordings.menu.retryModal.languageOptions.${language}`
                      )}
                    </AppText>
                    {isSelected ? (
                      <Lucide name="check" size={16} color={colors.primary} />
                    ) : null}
                  </Pressable>
                )
              })}
            </View>
          </Popover>
        </View>
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
  languageRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
  },
  consentText: {
    flexShrink: 1,
  },
  popover: { borderRadius: 12 },
  popoverContent: {
    padding: 4,
    minWidth: 140,
  },
  languageButton: {
    minHeight: 30,
    borderRadius: 8,
    paddingHorizontal: 8,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
  },
  languageButtonIcon: {
    marginBottom: -4,
  },
  languageButtonPressed: {
    backgroundColor: colors.backgroundSubtlePressed,
  },
  actionButton: {
    minHeight: 36,
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderRadius: 8,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  actionButtonPressed: {
    backgroundColor: colors.backgroundSubtlePressed,
  },
})
