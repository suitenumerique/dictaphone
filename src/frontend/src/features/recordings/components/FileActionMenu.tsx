import { DropdownMenu, DropdownMenuProps } from '@gouvfr-lasuite/ui-kit'
import {
  Button,
  Input,
  Modal,
  ModalSize,
  Select,
} from '@gouvfr-lasuite/cunningham-react'
import { useCallback, useMemo, useState } from 'react'
import { ApiFileItem } from '@/features/files/api/types.ts'
import { useTranslation } from 'react-i18next'
import { useDeleteFile } from '@/features/files/api/deleteFile.ts'
import { useHardDeleteFile } from '@/features/files/api/hardDeleteFile.ts'
import { useRestoreFile } from '@/features/files/api/restoreFile.ts'
import { usePartialUpdateFile } from '@/features/files/api/partialUpdateFile.ts'
import {
  addToast,
  ToasterItem,
} from '@/features/ui/components/toaster/Toaster.tsx'
import { getMainAiJobs } from '@/features/ai-jobs/utils/getMainAiJobs.ts'
import { useRetryWithLanguageMutation } from '@/features/ai-jobs/api/fetch.ts'
import { TTranscriptionLanguage } from '@/features/ai-jobs/api/types.ts'

const RETRY_LANGUAGES: TTranscriptionLanguage[] = ['fr', 'en', 'de', 'nl']

export function FileActionMenu({
  file,
  largeTrigger = false,
}: {
  file: ApiFileItem
  largeTrigger?: boolean
}) {
  const { t } = useTranslation(['recordings', 'shared'])
  const [isOpen, setIsOpen] = useState(false)
  const [title, setTitle] = useState(file.title)
  const [openRenameModal, setOpenRenameModal] = useState(false)
  const [openDeleteModal, setOpenDeleteModal] = useState(false)
  const [openRetryModal, setOpenRetryModal] = useState(false)
  const [retryLanguage, setRetryLanguage] =
    useState<TTranscriptionLanguage | null>(null)

  const deleteFileMutation = useDeleteFile()
  const hardDeleteFileMutation = useHardDeleteFile()
  const restoreFileMutation = useRestoreFile()
  const partialUpdateFileMutation = usePartialUpdateFile()
  const retryWithLanguageMutation = useRetryWithLanguageMutation()

  const { lastAiJobTranscript } = useMemo(
    () => getMainAiJobs(file.ai_jobs),
    [file.ai_jobs]
  )

  const isRetryDisabled = lastAiJobTranscript?.status === 'pending'

  const retryLanguages = useMemo(() => {
    return RETRY_LANGUAGES.map((language) => ({
      label: t(`actions.retryModal.languageOptions.${language}`),
      value: language,
      disabled:
        lastAiJobTranscript?.status === 'success'
          ? lastAiJobTranscript?.language === language
          : false,
    }))
  }, [lastAiJobTranscript?.language, lastAiJobTranscript?.status, t])

  const canOpenRetryModal =
    Boolean(lastAiJobTranscript?.id) &&
    !isRetryDisabled &&
    !file.ai_jobs
      .filter((el) => el.type === 'transcript')
      .some((el) => el.status === 'pending')

  const handleOpenRetryModal = useCallback(() => {
    if (!canOpenRetryModal) {
      return
    }
    setRetryLanguage(retryLanguages.find((el) => !el.disabled)!.value)
    setOpenRetryModal(true)
  }, [canOpenRetryModal, retryLanguages])

  const handleRetry = useCallback(() => {
    if (!lastAiJobTranscript?.id || !retryLanguage) {
      return
    }

    retryWithLanguageMutation.mutate(
      { id: lastAiJobTranscript.id, language: retryLanguage },
      {
        onSuccess: () => {
          setOpenRetryModal(false)
          setIsOpen(false)
          addToast(
            <ToasterItem type="info">
              <span>{t('actions.retry.success')}</span>
            </ToasterItem>
          )
        },
        onError: () =>
          addToast(
            <ToasterItem type="error">
              <span>{t('actions.retry.error')}</span>
            </ToasterItem>
          ),
      }
    )
  }, [lastAiJobTranscript, retryLanguage, retryWithLanguageMutation, t])

  const handleRename = useCallback(() => {
    partialUpdateFileMutation.mutate(
      { id: file.id, title },
      {
        onSuccess: () => {
          setOpenRenameModal(false)
          setIsOpen(false)
          addToast(
            <ToasterItem type="info">
              <span>{t('actions.rename.success')}</span>
            </ToasterItem>
          )
        },

        onError: () =>
          addToast(
            <ToasterItem type="error">
              <span>{t('actions.rename.error')}</span>
            </ToasterItem>
          ),
      }
    )
  }, [partialUpdateFileMutation, file.id, title, t])

  const handleDelete = useCallback(() => {
    deleteFileMutation.mutate(
      { fileId: file.id },
      {
        onSuccess: () => {
          setOpenDeleteModal(false)
          setIsOpen(false)
          addToast(
            <ToasterItem type="info">
              <span>{t('actions.delete.success')}</span>
            </ToasterItem>
          )
        },
        onError: () =>
          addToast(
            <ToasterItem type="error">
              <span>{t('actions.delete.error')}</span>
            </ToasterItem>
          ),
      }
    )
  }, [deleteFileMutation, file.id, t])

  const menuItems = useMemo(() => {
    const out: DropdownMenuProps['options'] = []
    if (file.abilities.partial_update) {
      out.push({
        label: t('actions.rename.label'),
        icon: <span className="material-icons">edit</span>,
        callback: () => setOpenRenameModal(true),
      })
    }

    if (lastAiJobTranscript?.id) {
      out.push({
        label: isRetryDisabled
          ? t('actions.retry.disabledPendingLabel')
          : t('actions.retry.label'),
        icon: <span className="material-icons">replay</span>,
        callback: canOpenRetryModal ? handleOpenRetryModal : () => undefined,
      })
    }

    if (file.abilities.destroy) {
      out.push({
        label: t('actions.delete.label'),
        icon: <span className="material-icons">delete</span>,
        callback: () => setOpenDeleteModal(true),
      })
    }

    if (file.abilities.restore) {
      out.push({
        label: t('actions.restore.label'),
        icon: <span className="material-icons">restore_from_trash</span>,
        callback: () =>
          restoreFileMutation.mutate(
            { fileId: file.id },
            {
              onSuccess: () =>
                addToast(
                  <ToasterItem type="info">
                    <span>{t('actions.restore.success')}</span>
                  </ToasterItem>
                ),
              onError: () =>
                addToast(
                  <ToasterItem type="error">
                    <span>{t('actions.restore.error')}</span>
                  </ToasterItem>
                ),
            }
          ),
      })
    }

    if (file.abilities.hard_delete) {
      out.push({
        label: t('actions.deletePermanently.label'),
        icon: <span className="material-icons">delete</span>,
        callback: () =>
          hardDeleteFileMutation.mutate(
            { fileId: file.id },
            {
              onSuccess: () => {
                addToast(
                  <ToasterItem type="info">
                    <span>{t('actions.deletePermanently.success')}</span>
                  </ToasterItem>
                )
              },
              onError: () =>
                addToast(
                  <ToasterItem type="error">
                    <span>{t('actions.deletePermanently.error')}</span>
                  </ToasterItem>
                ),
            }
          ),
      })
    }

    return out
  }, [
    file.abilities.destroy,
    file.abilities.hard_delete,
    file.abilities.partial_update,
    file.abilities.restore,
    file.id,
    hardDeleteFileMutation,
    handleOpenRetryModal,
    canOpenRetryModal,
    isRetryDisabled,
    lastAiJobTranscript?.id,
    restoreFileMutation,
    t,
  ])

  return (
    <div>
      <DropdownMenu
        options={menuItems}
        isOpen={isOpen}
        onOpenChange={setIsOpen}
      >
        {largeTrigger ? (
          <Button
            size="medium"
            variant="secondary"
            color="neutral"
            onClick={() => setIsOpen(!isOpen)}
            aria-label="more_actions"
            icon={<span className="material-icons more">more_horiz</span>}
          >
            {t('actions.cta')}
          </Button>
        ) : (
          <Button
            size="small"
            variant="tertiary"
            onClick={() => setIsOpen(!isOpen)}
            aria-label="more_actions"
            icon={<span className="material-icons more">more_horiz</span>}
          />
        )}
      </DropdownMenu>
      <Modal
        size={ModalSize.MEDIUM}
        isOpen={openDeleteModal}
        onClose={() => setOpenDeleteModal(false)}
        preventClose={deleteFileMutation.isPending}
        closeOnEsc={!deleteFileMutation.isPending}
        closeOnClickOutside={!deleteFileMutation.isPending}
        title={t('actions.deleteModal.title')}
        hideCloseButton={true}
        rightActions={
          <>
            <Button
              variant="bordered"
              onClick={() => setOpenDeleteModal(false)}
              disabled={deleteFileMutation.isPending}
              color="neutral"
            >
              {t('shared:actions.cancel')}
            </Button>
            <Button
              onClick={handleDelete}
              disabled={deleteFileMutation.isPending}
              color="error"
            >
              {t('actions.delete.label')}
            </Button>
          </>
        }
      >
        <p>{t('actions.deleteModal.description')}</p>
      </Modal>
      <Modal
        size={ModalSize.SMALL}
        isOpen={openRenameModal}
        onClose={() => setOpenRenameModal(false)}
        preventClose={partialUpdateFileMutation.isPending}
        closeOnEsc={!partialUpdateFileMutation.isPending}
        closeOnClickOutside={!partialUpdateFileMutation.isPending}
        title={t('actions.renameModal.title')}
        rightActions={
          <>
            <Button
              variant="bordered"
              onClick={() => setOpenRenameModal(false)}
              disabled={partialUpdateFileMutation.isPending}
              color="neutral"
            >
              {t('shared:actions.cancel')}
            </Button>
            <Button
              onClick={handleRename}
              disabled={
                partialUpdateFileMutation.isPending ||
                !title ||
                title.length > 255
              }
            >
              {t('actions.rename.label')}
            </Button>
          </>
        }
      >
        {/* We need to stop propagation on the input to prevent the player from capturing the keydown event*/}
        {/* eslint-disable-next-line jsx-a11y/no-static-element-interactions */}
        <div onKeyDown={(e) => e.stopPropagation()}>
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            label={t('actions.renameModal.label')}
            disabled={partialUpdateFileMutation.isPending}
            maxLength={255}
          />
        </div>
      </Modal>
      <Modal
        size={ModalSize.MEDIUM}
        isOpen={openRetryModal}
        onClose={() => setOpenRetryModal(false)}
        preventClose={retryWithLanguageMutation.isPending}
        closeOnEsc={!retryWithLanguageMutation.isPending}
        closeOnClickOutside={!retryWithLanguageMutation.isPending}
        title={t('actions.retryModal.title')}
        rightActions={
          <>
            <Button
              variant="bordered"
              onClick={() => setOpenRetryModal(false)}
              disabled={retryWithLanguageMutation.isPending}
              color="neutral"
            >
              {t('shared:actions.cancel')}
            </Button>
            <Button
              onClick={handleRetry}
              disabled={!retryLanguage || retryWithLanguageMutation.isPending}
            >
              {t('actions.retry.label')}
            </Button>
          </>
        }
      >
        <p>{t('actions.retryModal.description')}</p>
        <Select
          label={t('actions.retryModal.languageLabel')}
          value={retryLanguage ?? ''}
          onChange={(event) =>
            setRetryLanguage(event.target.value as TTranscriptionLanguage)
          }
          clearable={false}
          disabled={retryWithLanguageMutation.isPending}
          options={retryLanguages}
        />
      </Modal>
    </div>
  )
}
