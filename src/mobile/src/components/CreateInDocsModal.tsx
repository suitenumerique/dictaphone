import React from 'react'
import { ActivityIndicator, Modal, StyleSheet, View } from 'react-native'
import { useTranslation } from 'react-i18next'
import { AppText } from '@/components/AppText'
import { colors } from '@/components/colors'

type CreateInDocsModalProps = {
  isVisible: boolean
}

export function CreateInDocsModal({ isVisible }: CreateInDocsModalProps) {
  const { t } = useTranslation()

  return (
    <Modal
      visible={isVisible}
      transparent
      animationType="fade"
      onRequestClose={() => undefined}
    >
      <View style={styles.modalBackdrop}>
        <View style={styles.modalCard}>
          <AppText variant="heading" align="center">
            {t('recordings.createInDocsModal.title')}
          </AppText>
          <ActivityIndicator size="small" color={colors.primary} />
          <AppText
            variant="body"
            align="center"
            style={styles.modalDescription}
          >
            {t('recordings.createInDocsModal.description')}
          </AppText>
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
  modalDescription: {
    color: colors.textSecondary,
  },
})
