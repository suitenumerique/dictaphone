import React from 'react'
import {
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  View,
} from 'react-native'
import { Lucide } from '@react-native-vector-icons/lucide'
import { useTranslation } from 'react-i18next'
import { AppText } from '@/components/AppText'
import { colors } from '@/components/colors'
import type { TTranscriptionLanguage } from '@/features/ai-jobs/api/types'
import { TRANSCRIPTION_LANGUAGES } from '@/features/ai-jobs/constants'

type RetryTranscriptModalProps = {
  isVisible: boolean
  isPending: boolean
  selectedLanguage: TTranscriptionLanguage | null
  onSelectLanguage: (language: TTranscriptionLanguage) => void
  disabledLanguages?: TTranscriptionLanguage[]
  onClose: () => void
  onRetry: (language: TTranscriptionLanguage) => void
  mode: 'language' | 'retry'
}

export function RetryTranscriptModal({
  mode,
  isVisible,
  isPending,
  selectedLanguage,
  onSelectLanguage,
  disabledLanguages = [],
  onClose,
  onRetry,
}: RetryTranscriptModalProps) {
  const { t } = useTranslation()

  const closeModal = () => {
    if (!isPending) {
      onClose()
    }
  }

  return (
    <Modal
      animationType="fade"
      transparent
      visible={isVisible}
      onRequestClose={closeModal}
    >
      <View style={styles.modalBackdrop}>
        <Pressable style={StyleSheet.absoluteFill} onPress={closeModal} />
        <KeyboardAvoidingView
          style={styles.keyboardAvoidingView}
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          keyboardVerticalOffset={24}
        >
          <View style={styles.modalCard}>
            <AppText variant="heading">
              {t(
                mode === 'retry'
                  ? 'recordings.menu.retryModal.title'
                  : 'recordings.menu.retryModal.titleChangeLanguage'
              )}
            </AppText>
            <AppText variant="subtitle" style={styles.modalDescription}>
              {mode === 'retry'
                ? t('recordings.menu.retryModal.description')
                : t('recordings.menu.retryModal.descriptionChangeLanguage')}
            </AppText>
            <AppText variant="subtitle" color={colors.textPrimary}>
              {t('recordings.menu.retryModal.languageLabel')}
            </AppText>

            <View style={styles.optionsContainer}>
              {TRANSCRIPTION_LANGUAGES.map((language) => {
                const isDisabled = disabledLanguages.includes(language)
                const isSelected = selectedLanguage === language

                return (
                  <Pressable
                    key={language}
                    onPress={() => onSelectLanguage(language)}
                    disabled={isPending || isDisabled}
                    style={({ pressed }) => [
                      styles.optionButton,
                      isSelected && styles.optionButtonSelected,
                      (isPending || isDisabled) && styles.optionButtonDisabled,
                      pressed &&
                        !isPending &&
                        !isDisabled &&
                        styles.optionButtonPressed,
                    ]}
                  >
                    <AppText
                      color={
                        isDisabled
                          ? colors.neutralSecondary
                          : colors.textPrimary
                      }
                    >
                      {t(
                        `recordings.menu.retryModal.languageOptions.${language}`
                      )}
                    </AppText>
                    {isSelected && (
                      <Lucide name="check" size={18} color={colors.primary} />
                    )}
                  </Pressable>
                )
              })}
            </View>

            {mode === 'language' && (
              <AppText>{t('recordings.menu.retryModal.extra')}</AppText>
            )}

            <View style={styles.modalActions}>
              <Pressable
                onPress={closeModal}
                style={({ pressed }) => [
                  styles.secondaryButton,
                  pressed && styles.secondaryButtonPressed,
                ]}
                disabled={isPending}
              >
                <AppText>{t('recordings.deleteCancel')}</AppText>
              </Pressable>
              <Pressable
                onPress={() => {
                  if (selectedLanguage) {
                    onRetry(selectedLanguage)
                  }
                }}
                style={({ pressed }) => [
                  styles.primaryButton,
                  pressed && styles.primaryButtonPressed,
                  (!selectedLanguage || isPending) && styles.buttonDisabled,
                ]}
                disabled={!selectedLanguage || isPending}
              >
                <AppText variant="button">
                  {mode === 'retry'
                    ? t('recordings.menu.retryModal.retryMainAction')
                    : t('recordings.menu.retryModal.changeLanguageMainAction')}
                </AppText>
              </Pressable>
            </View>
          </View>
        </KeyboardAvoidingView>
      </View>
    </Modal>
  )
}

const styles = StyleSheet.create({
  modalBackdrop: {
    flex: 1,
    backgroundColor: colors.overlayBackdrop,
    justifyContent: 'center',
    paddingHorizontal: 20,
  },
  keyboardAvoidingView: {
    width: '100%',
    alignSelf: 'center',
  },
  modalCard: {
    backgroundColor: colors.backgroundBase,
    borderRadius: 12,
    padding: 18,
    gap: 12,
  },
  modalDescription: {
    marginTop: -2,
  },
  optionsContainer: {
    gap: 8,
    marginTop: -4,
  },
  optionButton: {
    minHeight: 42,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.surfacePrimary,
    backgroundColor: colors.backgroundBase,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
  },
  optionButtonPressed: {
    backgroundColor: colors.backgroundSubtlePressed,
  },
  optionButtonSelected: {
    borderColor: colors.primary,
    backgroundColor: colors.backgroundSubtle,
  },
  optionButtonDisabled: {
    opacity: 0.6,
  },
  modalActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 10,
    marginTop: 2,
  },
  secondaryButton: {
    minWidth: 92,
    height: 38,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.surfacePrimary,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 12,
    backgroundColor: colors.backgroundSubtle,
  },
  secondaryButtonPressed: {
    backgroundColor: colors.backgroundSubtlePressed,
  },
  primaryButton: {
    minWidth: 92,
    height: 38,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 16,
    backgroundColor: colors.primary,
  },
  primaryButtonPressed: {
    opacity: 0.9,
  },
  buttonDisabled: {
    opacity: 0.4,
  },
})
