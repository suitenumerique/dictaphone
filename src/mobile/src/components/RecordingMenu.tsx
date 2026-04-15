import React, { useCallback, useMemo, useState } from 'react';
import {
  Alert,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import Popover from 'react-native-popover-view';
import { Lucide } from '@react-native-vector-icons/lucide';
import { useTranslation } from 'react-i18next';
import { useDeleteFile } from '@/features/files/api/deleteFile';
import { usePartialUpdateFile } from '@/features/files/api/partialUpdateFile';

type RecordingMenuProps = {
  fileId: string;
  currentTitle: string;
  onDeleted: () => void;
};

export default function RecordingMenu({
  fileId,
  currentTitle,
  onDeleted,
}: RecordingMenuProps) {
  const { t } = useTranslation();
  const [isPopoverVisible, setIsPopoverVisible] = useState(false);
  const [isRenameModalVisible, setIsRenameModalVisible] = useState(false);
  const [draftTitle, setDraftTitle] = useState(currentTitle);

  const deleteMutation = useDeleteFile();
  const renameMutation = usePartialUpdateFile();

  const isBusy = deleteMutation.isPending || renameMutation.isPending;
  const sanitizedTitle = useMemo(() => draftTitle.trim(), [draftTitle]);

  const openRenameModal = useCallback(() => {
    setIsPopoverVisible(false);
    setDraftTitle(currentTitle);
    setIsRenameModalVisible(true);
  }, [currentTitle]);

  const closeRenameModal = useCallback(() => {
    if (!renameMutation.isPending) {
      setIsRenameModalVisible(false);
    }
  }, [renameMutation.isPending]);

  const onConfirmDelete = useCallback(() => {
    setIsPopoverVisible(false);
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
            await deleteMutation.mutateAsync({ fileId });
            onDeleted();
          } catch {
            Alert.alert(
              t('recordings.menu.errorTitle'),
              t('recordings.menu.deleteError'),
            );
          }
        },
      },
    ]);
  }, [deleteMutation, fileId, onDeleted, t]);

  const onConfirmRename = useCallback(async () => {
    if (!sanitizedTitle) {
      return;
    }
    try {
      await renameMutation.mutateAsync({ id: fileId, title: sanitizedTitle });
      setIsRenameModalVisible(false);
    } catch {
      Alert.alert(
        t('recordings.menu.errorTitle'),
        t('recordings.menu.renameError'),
      );
    }
  }, [fileId, renameMutation, sanitizedTitle, t]);

  return (
    <>
      <View style={styles.container}>
        <Popover
          isVisible={isPopoverVisible}
          arrowSize={{ width: 0, height: 0 }}
          popoverStyle={styles.popover}
          onRequestClose={() => setIsPopoverVisible(false)}
          from={
            <Pressable
              style={styles.iconButton}
              onPress={() => setIsPopoverVisible(true)}
              hitSlop={10}
            >
              <Lucide size={26} name="ellipsis" color="#3E5DE7" />
            </Pressable>
          }
        >
          <View style={styles.popoverContent}>
            <Pressable
              style={styles.actionButton}
              onPress={openRenameModal}
              disabled={isBusy}
            >
              <Lucide name="pencil" size={15} color="#222631" />
              <Text style={styles.actionText}>
                {t('recordings.menu.rename')}
              </Text>
            </Pressable>
            <Pressable
              style={styles.actionButton}
              onPress={onConfirmDelete}
              disabled={isBusy}
            >
              <Lucide name="trash-2" size={15} color="#B42318" />
              <Text style={[styles.actionText, styles.deleteText]}>
                {t('recordings.delete')}
              </Text>
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
            <Text style={styles.modalTitle}>
              {t('recordings.menu.renameTitle')}
            </Text>
            <Text style={styles.modalDescription}>
              {t('recordings.menu.renameDescription')}
            </Text>

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
                <Text style={styles.secondaryButtonText}>
                  {t('recordings.deleteCancel')}
                </Text>
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
                <Text style={styles.primaryButtonText}>
                  {t('recordings.menu.save')}
                </Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  container: {
    justifyContent: 'center',
    alignItems: 'flex-end',
  },
  iconButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
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
  actionText: {
    color: '#222631',
    fontWeight: '600',
  },
  deleteText: {
    color: '#B42318',
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 42, 0.45)',
    paddingHorizontal: 24,
    justifyContent: 'center',
  },
  modalCard: {
    borderRadius: 16,
    backgroundColor: '#FFFFFF',
    padding: 18,
    gap: 10,
  },
  modalTitle: {
    color: '#0F172A',
    fontSize: 18,
    fontWeight: '700',
  },
  modalDescription: {
    color: '#475467',
    fontSize: 13,
    lineHeight: 18,
  },
  input: {
    marginTop: 2,
    borderWidth: 1,
    borderColor: '#D0D5DD',
    borderRadius: 10,
    minHeight: 44,
    paddingHorizontal: 12,
    color: '#0F172A',
    fontSize: 15,
    fontWeight: '500',
    backgroundColor: '#F8FAFC',
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
    borderColor: '#D0D5DD',
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 14,
  },
  secondaryButtonPressed: {
    backgroundColor: '#F2F4F7',
  },
  secondaryButtonText: {
    color: '#344054',
    fontWeight: '600',
  },
  primaryButton: {
    minHeight: 40,
    borderRadius: 10,
    backgroundColor: '#3E5DE7',
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 14,
    minWidth: 84,
  },
  primaryButtonPressed: {
    backgroundColor: '#304DDF',
  },
  primaryButtonText: {
    color: '#FFFFFF',
    fontWeight: '700',
  },
  buttonDisabled: {
    opacity: 0.5,
  },
});
