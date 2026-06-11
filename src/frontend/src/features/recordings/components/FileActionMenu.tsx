import { DropdownMenu, DropdownMenuProps } from '@gouvfr-lasuite/ui-kit'
import {
  ArrowUpRight,
  Copy,
  Download,
  Edit,
  Language,
  Trash,
  UndoCircle,
} from '@gouvfr-lasuite/ui-kit/icons'
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
import {
  getTranscript,
  useOpenInDocsMutation,
  useRetryWithLanguageMutation,
} from '@/features/ai-jobs/api/fetch.ts'
import { TTranscriptionLanguage } from '@/features/ai-jobs/api/types.ts'
import { useLocation } from 'wouter'
import {
  buildTranscriptMarkdown,
  buildTranscriptSrt,
  buildTranscriptViewSegments,
} from '@/features/ai-jobs/utils/transcript.ts'

const RETRY_LANGUAGES: TTranscriptionLanguage[] = ['fr', 'en', 'de', 'nl']
type ExportFormat = 'markdown' | 'srt' | 'json'

const sanitizeFileName = (value: string) => {
  const sanitized = value
    .trim()
    .replace(/[\\/:*?"<>|]+/g, '-')
    .replace(/\s+/g, ' ')
  return sanitized || 'transcript'
}

const downloadTextFile = ({
  filename,
  content,
  mimeType,
}: {
  filename: string
  content: string
  mimeType: string
}) => {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.setTimeout(() => URL.revokeObjectURL(url), 10000)
}

export function FileActionMenu({
  file,
  largeTrigger = false,
  showCopyText = true,
  showOpenInDocs = true,
}: {
  file: ApiFileItem
  largeTrigger?: boolean
  showCopyText?: boolean
  showOpenInDocs?: boolean
}) {
  const { t } = useTranslation(['recordings', 'shared'])
  const [isOpen, setIsOpen] = useState(false)
  const [title, setTitle] = useState(file.title)
  const [openRenameModal, setOpenRenameModal] = useState(false)
  const [openDeleteModal, setOpenDeleteModal] = useState(false)
  const [openRetryModal, setOpenRetryModal] = useState<
    false | 'retry' | 'changeLanguage'
  >(false)
  const [openExportModal, setOpenExportModal] = useState(false)
  const [isCopyingText, setIsCopyingText] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const [exportFormat, setExportFormat] = useState<ExportFormat>('srt')
  const [retryLanguage, setRetryLanguage] =
    useState<TTranscriptionLanguage | null>(null)
  const [, navigate] = useLocation()

  const deleteFileMutation = useDeleteFile()
  const hardDeleteFileMutation = useHardDeleteFile()
  const restoreFileMutation = useRestoreFile()
  const partialUpdateFileMutation = usePartialUpdateFile()
  const retryWithLanguageMutation = useRetryWithLanguageMutation()

  const { lastAiJobTranscript } = useMemo(
    () => getMainAiJobs(file.ai_jobs),
    [file.ai_jobs]
  )
  const isRetryPending = lastAiJobTranscript?.status === 'pending'

  const retryLanguages = useMemo(() => {
    return RETRY_LANGUAGES.map((language) => ({
      label: t(`actions.changeLanguageModal.languageOptions.${language}`),
      value: language,
      disabled:
        lastAiJobTranscript?.status === 'success'
          ? lastAiJobTranscript?.language === language
          : false,
    }))
  }, [lastAiJobTranscript?.language, lastAiJobTranscript?.status, t])

  const canOpenRetryModal =
    file.lifecycle_state === 'active' &&
    Boolean(lastAiJobTranscript?.id) &&
    !isRetryPending &&
    !file.ai_jobs
      .filter((el) => el.type === 'transcript')
      .some((el) => el.status === 'pending')

  const handleOpenRetryModal = useCallback(
    (mode: 'changeLanguage' | 'retry') => {
      if (!canOpenRetryModal) {
        return
      }
      setRetryLanguage(retryLanguages.find((el) => !el.disabled)!.value)
      setOpenRetryModal(mode)
    },
    [canOpenRetryModal, retryLanguages]
  )

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
          navigate('/recordings')
        },
        onError: () =>
          addToast(
            <ToasterItem type="error">
              <span>{t('actions.delete.error')}</span>
            </ToasterItem>
          ),
      }
    )
  }, [deleteFileMutation, file.id, navigate, t])

  const openInDocs = useOpenInDocsMutation()
  const handleOpenInDocs = useCallback(() => {
    if (
      lastAiJobTranscript?.id &&
      lastAiJobTranscript.status === 'success' &&
      lastAiJobTranscript.docs_app_id
    ) {
      openInDocs.mutate(lastAiJobTranscript, {
        onSuccess: (res) => {
          window.open(res.doc_url, '_blank')
        },
      })
    }
  }, [lastAiJobTranscript, openInDocs])

  const handleCopyText = useCallback(() => {
    if (lastAiJobTranscript?.status !== 'success' || isCopyingText) {
      return
    }

    const copyTranscript = async () => {
      setIsCopyingText(true)
      try {
        const transcript = await getTranscript(lastAiJobTranscript)
        const markdown = buildTranscriptMarkdown({
          title: file.title,
          transcriptSegments: buildTranscriptViewSegments(transcript),
          speakerLabel: t('transcript.speaker'),
        })

        if (!markdown) {
          addToast(
            <ToasterItem type="error">{t('transcript.copyError')}</ToasterItem>
          )
          return
        }

        await navigator.clipboard.writeText(markdown)
        setIsOpen(false)
        addToast(
          <ToasterItem type="info">{t('transcript.copySuccess')}</ToasterItem>
        )
      } catch {
        addToast(
          <ToasterItem type="error">{t('transcript.copyError')}</ToasterItem>
        )
      } finally {
        setIsCopyingText(false)
      }
    }

    void copyTranscript()
  }, [file.title, isCopyingText, lastAiJobTranscript, t])

  const exportFormats = useMemo(
    () => [
      {
        value: 'srt' as const,
        label: t('actions.exportModal.formatOptions.srt'),
      },
      {
        value: 'markdown' as const,
        label: t('actions.exportModal.formatOptions.markdown'),
      },
      {
        value: 'json' as const,
        label: t('actions.exportModal.formatOptions.json'),
      },
    ],
    [t]
  )

  const handleExport = useCallback(() => {
    if (lastAiJobTranscript?.status !== 'success' || isExporting) {
      return
    }

    const runExport = async () => {
      setIsExporting(true)
      try {
        const transcript = await getTranscript(lastAiJobTranscript)
        const filenameBase = sanitizeFileName(file.title || file.filename)

        if (exportFormat === 'markdown') {
          const markdown = buildTranscriptMarkdown({
            title: file.title,
            transcriptSegments: buildTranscriptViewSegments(transcript),
            speakerLabel: t('transcript.speaker'),
          })
          if (!markdown) {
            throw new Error('No transcript markdown')
          }
          downloadTextFile({
            filename: `${filenameBase}.md`,
            content: markdown,
            mimeType: 'text/markdown;charset=utf-8',
          })
        }

        if (exportFormat === 'srt') {
          const srt = buildTranscriptSrt(transcript, {
            speakerLabel: t('transcript.speaker'),
          })
          if (!srt) {
            throw new Error('No transcript srt')
          }
          downloadTextFile({
            filename: `${filenameBase}.srt`,
            content: srt,
            mimeType: 'text/plain;charset=utf-8',
          })
        }

        if (exportFormat === 'json') {
          const rawJson = JSON.stringify(
            buildTranscriptViewSegments(transcript),
            null,
            2
          )
          downloadTextFile({
            filename: `${filenameBase}.json`,
            content: rawJson,
            mimeType: 'application/json;charset=utf-8',
          })
        }

        setOpenExportModal(false)
        setIsOpen(false)
        addToast(
          <ToasterItem type="info">{t('actions.export.success')}</ToasterItem>
        )
      } catch {
        addToast(
          <ToasterItem type="error">{t('actions.export.error')}</ToasterItem>
        )
      } finally {
        setIsExporting(false)
      }
    }

    void runExport()
  }, [
    exportFormat,
    file.filename,
    file.title,
    isExporting,
    lastAiJobTranscript,
    t,
  ])

  const menuItems = useMemo(() => {
    const out: DropdownMenuProps['options'] = []
    if (showOpenInDocs) {
      out.push({
        label: t('transcript.openInDocsCta'),
        icon: <ArrowUpRight size="small" />,
        callback: handleOpenInDocs,
        isDisabled: !lastAiJobTranscript?.docs_app_id,
      })
    }
    if (showCopyText) {
      out.push({
        label: t('shared:actions.copyText'),
        icon: <Copy size="small" />,
        callback: handleCopyText,
        isDisabled: lastAiJobTranscript?.status !== 'success' || isCopyingText,
      })
    }

    out.push({
      label: t('actions.export.label'),
      icon: <Download size="small" />,
      callback: () => setOpenExportModal(true),
      isDisabled: lastAiJobTranscript?.status !== 'success',
    })

    out.push({ type: 'separator' })

    if (lastAiJobTranscript?.id && lastAiJobTranscript?.status === 'failed') {
      out.push({
        label: isRetryPending
          ? t('actions.retry.disabledPendingLabel')
          : t('actions.retry.label'),
        isDisabled: file.lifecycle_state !== 'active' || isRetryPending,
        icon: <UndoCircle size="small" />,
        callback: canOpenRetryModal
          ? () => handleOpenRetryModal('retry')
          : () => undefined,
      })
    }

    if (lastAiJobTranscript?.id && lastAiJobTranscript?.status === 'success') {
      out.push({
        label: t('actions.changeLanguage.label'),
        subText: t('actions.changeLanguage.subLabel'),
        isDisabled: file.lifecycle_state !== 'active' || isRetryPending,
        icon: <Language size="small" />,
        callback: canOpenRetryModal
          ? () => handleOpenRetryModal('changeLanguage')
          : () => undefined,
      })
    }

    if (file.abilities.partial_update) {
      out.push({
        label: t('actions.rename.label'),
        icon: <Edit size="small" />,
        callback: () => setOpenRenameModal(true),
      })
    }

    if (file.abilities.destroy) {
      out.push({
        label: t('actions.delete.label'),
        icon: <Trash size="small" />,
        callback: () => setOpenDeleteModal(true),
      })
    }

    if (file.abilities.restore) {
      out.push({
        label: t('actions.restore.label'),
        icon: (
          <span className="material-icons" aria-hidden="true">
            restore_from_trash
          </span>
        ),
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
        icon: (
          <span className="material-icons" aria-hidden="true">
            delete
          </span>
        ),
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
    showOpenInDocs,
    showCopyText,
    t,
    lastAiJobTranscript?.status,
    lastAiJobTranscript?.id,
    lastAiJobTranscript?.docs_app_id,
    file.abilities.partial_update,
    file.abilities.destroy,
    file.abilities.restore,
    file.abilities.hard_delete,
    file.lifecycle_state,
    file.id,
    handleOpenInDocs,
    handleCopyText,
    isCopyingText,
    isRetryPending,
    canOpenRetryModal,
    handleOpenRetryModal,
    restoreFileMutation,
    hardDeleteFileMutation,
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
            color="brand"
            onClick={() => setIsOpen(!isOpen)}
            aria-label={t('actions.moreOptionsAriaLabel', {
              title: file.title || file.filename,
            })}
            icon={
              <span className="material-icons more" aria-hidden="true">
                more_horiz
              </span>
            }
          >
            {t('actions.cta')}
          </Button>
        ) : (
          <Button
            size="small"
            variant="tertiary"
            color="neutral"
            onClick={() => setIsOpen(!isOpen)}
            aria-label={t('actions.moreOptionsAriaLabel', {
              title: file.title || file.filename,
            })}
            icon={
              <span className="material-icons more" aria-hidden="true">
                more_horiz
              </span>
            }
          />
        )}
      </DropdownMenu>
      <Modal
        size={ModalSize.MEDIUM}
        isOpen={openExportModal}
        onClose={() => setOpenExportModal(false)}
        preventClose={isExporting}
        closeOnEsc={!isExporting}
        closeOnClickOutside={!isExporting}
        title={t('actions.exportModal.title')}
        rightActions={
          <>
            <Button
              variant="bordered"
              onClick={() => setOpenExportModal(false)}
              disabled={isExporting}
              color="neutral"
            >
              {t('shared:actions.cancel')}
            </Button>
            <Button onClick={handleExport} disabled={isExporting}>
              {t('actions.exportModal.submit')}
            </Button>
          </>
        }
      >
        <p>{t('actions.exportModal.description')}</p>
        <Select
          label={t('actions.exportModal.formatLabel')}
          value={exportFormat}
          onChange={(event) =>
            setExportFormat(event.target.value as ExportFormat)
          }
          clearable={false}
          disabled={isExporting}
          options={exportFormats}
        />
      </Modal>
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
        size={ModalSize.SMALL}
        isOpen={openRetryModal !== false}
        onClose={() => setOpenRetryModal(false)}
        preventClose={retryWithLanguageMutation.isPending}
        closeOnEsc={!retryWithLanguageMutation.isPending}
        closeOnClickOutside={!retryWithLanguageMutation.isPending}
        title={t(
          openRetryModal === 'retry'
            ? 'actions.retryModal.title'
            : 'actions.changeLanguageModal.title'
        )}
        subtitle={t(
          openRetryModal === 'retry'
            ? 'actions.retryModal.description'
            : 'actions.changeLanguageModal.description'
        )}
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
        <br />
        <Select
          label={t('actions.changeLanguageModal.selectLangLabel')}
          value={retryLanguage ?? ''}
          onChange={(event) =>
            setRetryLanguage(event.target.value as TTranscriptionLanguage)
          }
          clearable={false}
          disabled={retryWithLanguageMutation.isPending}
          options={retryLanguages}
        />
        {openRetryModal === 'changeLanguage' && (
          <p>{t('actions.changeLanguageModal.extra')}</p>
        )}
      </Modal>
    </div>
  )
}
