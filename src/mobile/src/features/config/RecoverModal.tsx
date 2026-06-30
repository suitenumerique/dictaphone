import React, { useState } from 'react'
import {
  ActivityIndicator,
  Modal,
  Pressable,
  StyleSheet,
  View,
} from 'react-native'
import { useTranslation } from 'react-i18next'
import { AppText } from '@/components/AppText'
import { colors } from '@/components/colors'
import { useRecordingsStore } from '@/services/storage'

export function RecoverModal() {
  const { t } = useTranslation()
  const recoverFilesStatus = useRecordingsStore(
    (state) => state.recoverFilesStatus
  )
  const [dismissRunning, setDismissRunning] = useState(false)
  const [dismissedRecoveredSignature, setDismissedRecoveredSignature] =
    useState<string | null>(null)

  const recovered =
    recoverFilesStatus.status === 'done' ? recoverFilesStatus.recovered : []
  const recoveredSignature =
    recoverFilesStatus.status === 'done'
      ? recoverFilesStatus.recovered.join('\n')
      : ''

  const showRunningModal =
    recoverFilesStatus.status === 'running' && !dismissRunning
  const showRecoveredModal =
    recoverFilesStatus.status === 'done' &&
    recovered.length > 0 &&
    dismissedRecoveredSignature !== recoveredSignature
  const showModal = showRunningModal || showRecoveredModal

  return (
    <Modal
      visible={showModal}
      transparent
      animationType="fade"
      onRequestClose={() => {
        if (showRunningModal) {
          setDismissRunning(true)
        }
      }}
    >
      <View style={styles.modalBackdrop}>
        <View style={styles.modalCard}>
          <AppText variant="heading" align="center">
            {t('recordings.recoverModal.title')}
          </AppText>

          {showRunningModal ? (
            <View style={styles.runningSection}>
              <ActivityIndicator size="small" color={colors.primary} />
              <AppText
                variant="body"
                align="center"
                style={styles.modalDescription}
              >
                {t('recordings.recoverModal.runningDescription')}
              </AppText>
            </View>
          ) : null}

          {showRecoveredModal ? (
            <View style={styles.recoveredSection}>
              <AppText
                variant="body"
                align="center"
                style={styles.modalDescription}
              >
                {t('recordings.recoverModal.doneDescription')}
              </AppText>
              <View style={styles.recoveredList}>
                {recovered.map((fileName) => (
                  <AppText
                    key={fileName}
                    variant="body"
                    style={styles.recoveredItem}
                  >
                    {`• ${fileName}`}
                  </AppText>
                ))}
              </View>
            </View>
          ) : null}

          <View style={styles.modalActions}>
            {showRunningModal ? (
              <Pressable
                onPress={() => setDismissRunning(true)}
                style={({ pressed }) => [
                  styles.secondaryButton,
                  pressed && styles.secondaryButtonPressed,
                ]}
              >
                <AppText variant="bodyMedium" align="center">
                  {t('recordings.recoverModal.close')}
                </AppText>
              </Pressable>
            ) : null}
            {showRecoveredModal ? (
              <Pressable
                onPress={() =>
                  setDismissedRecoveredSignature(recoveredSignature)
                }
                style={({ pressed }) => [
                  styles.primaryButton,
                  pressed && styles.primaryButtonPressed,
                ]}
              >
                <AppText variant="button" align="center">
                  {t('recordings.recoverModal.ok')}
                </AppText>
              </Pressable>
            ) : null}
          </View>
        </View>
      </View>
    </Modal>
  )
}

const styles = StyleSheet.create({
  modalBackdrop: {
    flex: 1,
    backgroundColor: colors.overlayBackdrop,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 24,
  },
  modalCard: {
    width: '100%',
    borderRadius: 16,
    backgroundColor: colors.backgroundBase,
    paddingHorizontal: 20,
    paddingVertical: 20,
    gap: 12,
  },
  runningSection: {
    alignItems: 'center',
    gap: 10,
  },
  recoveredSection: {
    gap: 8,
  },
  modalDescription: {
    color: colors.textSecondary,
  },
  recoveredList: {
    gap: 4,
  },
  recoveredItem: {
    color: colors.textPrimary,
  },
  modalActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    alignItems: 'center',
    gap: 8,
    marginTop: 4,
  },
  primaryButton: {
    minHeight: 42,
    borderRadius: 12,
    backgroundColor: colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 16,
  },
  primaryButtonPressed: {
    backgroundColor: colors.primaryPressed,
  },
  secondaryButton: {
    minHeight: 42,
    borderRadius: 12,
    backgroundColor: colors.backgroundNeutralSecondary,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 16,
  },
  secondaryButtonPressed: {
    backgroundColor: colors.backgroundNeutralSecondaryPressed,
  },
})
