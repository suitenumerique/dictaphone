import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Modal,
  Pressable,
  StyleSheet,
  TextInput,
  View,
} from 'react-native'
import Popover from 'react-native-popover-view'
import { Lucide } from '@react-native-vector-icons/lucide'
import { useTranslation } from 'react-i18next'
import { useDeleteFile } from '@/features/files/api/deleteFile'
import { usePartialUpdateFile } from '@/features/files/api/partialUpdateFile'
import { AppText } from './AppText'
import { colors } from './colors'

type RecordingMenuProps = {
  fileId: string
  currentTitle: string
  onDeleted: () => void
}

export default function RecordingMenu({
  fileId,
  currentTitle,
  onDeleted,
}: RecordingMenuProps) {
  const { t } = useTranslation()
  const [isPopoverVisible, setIsPopoverVisible] = useState(false)
  const [isRenameModalVisible, setIsRenameModalVisible] = useState(false)
  const [draftTitle, setDraftTitle] = useState(currentTitle)
  const [pendingRename, setPendingRename] = useState(false)

  const deleteMutation = useDeleteFile()
  const renameMutation = usePartialUpdateFile()

  const isBusy = deleteMutation.isPending || renameMutation.isPending
  const sanitizedTitle = useMemo(() => draftTitle.trim(), [draftTitle])

  useEffect(() => {
    if (isRenameModalVisible) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setDraftTitle(currentTitle)
    }
  }, [currentTitle, isRenameModalVisible])

  const openRenameModal = useCallback(() => {
    setPendingRename(true)
    setIsPopoverVisible(false)
  }, [])

  const handlePopoverCloseComplete = useCallback(() => {
    if (pendingRename) {
      setPendingRename(false)

      // Hack for opening the rename modal to work on iOS
      setTimeout(() => {
        setIsRenameModalVisible(true)
      }, 50)
    }
  }, [pendingRename])

  const closeRenameModal = useCallback(() => {
    if (!renameMutation.isPending) {
      setIsRenameModalVisible(false)
    }
  }, [renameMutation.isPending])

  const onConfirmDelete = useCallback(() => {
    setIsPopoverVisible(false)
    Alert.alert(t('recordings.deleteTitle'), t('recordings.deleteMessage'), [
      {
        style: 'cancel',
        text: t('recordings.deleteCancel'),
      },
      {
        style: 'destructive',
        text: t('recordings.deleteConfirm'),
        onPress: async () => {
          try {
            await deleteMutation.mutateAsync({ fileId })
            onDeleted()
          } catch {
            Alert.alert(
              t('recordings.menu.errorTitle'),
              t('recordings.menu.deleteError')
            )
          }
        },
      },
    ])
  }, [deleteMutation, fileId, onDeleted, t])

  const onConfirmRename = useCallback(async () => {
    if (!sanitizedTitle) {
      return
    }
    try {
      await renameMutation.mutateAsync({ id: fileId, title: sanitizedTitle })
      setIsRenameModalVisible(false)
    } catch {
      Alert.alert(
        t('recordings.menu.errorTitle'),
        t('recordings.menu.renameError')
      )
    }
  }, [fileId, renameMutation, sanitizedTitle, t])

  return (
    <>
      <View style={styles.container}>
        <Popover
          isVisible={isPopoverVisible}
          arrowSize={{ width: 0, height: 0 }}
          popoverStyle={styles.popover}
          onRequestClose={() => setIsPopoverVisible(false)}
          onCloseComplete={handlePopoverCloseComplete}
          from={
            <Pressable
              style={({ pressed }) => [
                pressed && styles.iconButtonPressed,
                styles.iconButton,
              ]}
              onPress={() => setIsPopoverVisible(true)}
              hitSlop={10}
            >
              <Lucide size={26} name="ellipsis" color={colors.primary} />
            </Pressable>
          }
        >
          <View style={styles.popoverContent}>
            <Pressable
              style={styles.actionButton}
              onPress={openRenameModal}
              disabled={isBusy}
            >
              <Lucide name="pencil" size={15} color={colors.textPrimary} />
              <AppText
                variant="body"
                color={colors.textPrimary}
                style={styles.fixMarginBottom}
              >
                {t('recordings.menu.rename')}
              </AppText>
            </Pressable>
            <Pressable
              style={styles.actionButton}
              onPress={onConfirmDelete}
              disabled={isBusy}
            >
              <Lucide name="trash-2" size={15} color={colors.errorSecondary} />
              <AppText
                color={colors.errorSecondary}
                style={styles.fixMarginBottom}
              >
                {t('recordings.delete')}
              </AppText>
            </Pressable>
          </View>
        </Popover>
      </View>

      <Modal
        animationType="fade"
        transparent
        visible={isRenameModalVisible}
        onRequestClose={closeRenameModal}
      >
        <View style={styles.modalBackdrop}>
          <Pressable
            style={StyleSheet.absoluteFill}
            onPress={closeRenameModal}
          />
          <View style={styles.modalCard}>
            <AppText variant="heading">
              {t('recordings.menu.renameTitle')}
            </AppText>
            <AppText variant="subtitle" style={styles.modalDescription}>
              {t('recordings.menu.renameDescription')}
            </AppText>

            <TextInput
              autoFocus
              value={draftTitle}
              onChangeText={setDraftTitle}
              placeholder={t('recordings.menu.renamePlaceholder')}
              style={styles.input}
              editable={!renameMutation.isPending}
              maxLength={120}
            />

            <View style={styles.modalActions}>
              <Pressable
                onPress={closeRenameModal}
                style={({ pressed }) => [
                  styles.secondaryButton,
                  pressed && styles.secondaryButtonPressed,
                ]}
                disabled={renameMutation.isPending}
              >
                <AppText>{t('recordings.deleteCancel')}</AppText>
              </Pressable>
              <Pressable
                onPress={onConfirmRename}
                style={({ pressed }) => [
                  styles.primaryButton,
                  pressed && styles.primaryButtonPressed,
                  (!sanitizedTitle || renameMutation.isPending) &&
                    styles.buttonDisabled,
                ]}
                disabled={!sanitizedTitle || renameMutation.isPending}
              >
                <AppText variant="button">{t('recordings.menu.save')}</AppText>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </>
  )
}

const styles = StyleSheet.create({
  container: {
    justifyContent: 'center',
    alignItems: 'flex-end',
  },
  iconButton: {
    display: 'flex',
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconButtonPressed: {
    backgroundColor: colors.backgroundSubtlePressed,
  },
  fixMarginBottom: {
    marginTop: -3,
  },
  popover: { borderRadius: 12 },
  popoverContent: {
    padding: 4,
    gap: 2,
  },
  actionButton: {
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: colors.overlayBackdrop,
    paddingHorizontal: 24,
    justifyContent: 'center',
  },
  modalCard: {
    borderRadius: 16,
    backgroundColor: colors.backgroundBase,
    padding: 18,
    gap: 10,
  },
  modalDescription: {
    lineHeight: 18,
  },
  input: {
    marginTop: 2,
    borderWidth: 1,
    borderColor: colors.surfacePrimary,
    borderRadius: 10,
    minHeight: 44,
    paddingHorizontal: 12,
    fontSize: 15,
    backgroundColor: colors.backgroundSubtle,
  },
  modalActions: {
    marginTop: 4,
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 10,
  },
  secondaryButton: {
    minHeight: 40,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.surfacePrimary,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 14,
  },
  secondaryButtonPressed: {
    backgroundColor: colors.backgroundSubtlePressed,
  },
  primaryButton: {
    minHeight: 40,
    borderRadius: 10,
    backgroundColor: colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 14,
    minWidth: 84,
  },
  primaryButtonPressed: {
    backgroundColor: colors.primaryPressed,
  },
  buttonDisabled: {
    opacity: 0.5,
  },
})
