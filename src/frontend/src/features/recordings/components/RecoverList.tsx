import {
  createLocalFileFromChunkStore,
  useLocalRecordingsStore,
} from '@/features/recordings/store/useLocalRecordingsStore.ts'
import { Button, Tooltip } from '@gouvfr-lasuite/cunningham-react'
import { intervalToDuration } from 'date-fns'
import { Fragment, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  DropdownMenu,
  HorizontalSeparator,
  Spinner,
} from '@gouvfr-lasuite/ui-kit'
import { Download, Retry, Trash, Warning } from '@gouvfr-lasuite/ui-kit/icons'
import { CircularProgress } from '@/features/ui/components/circular-progress/CircularProgress'

const downloadFile = (file: File) => {
  const objectUrl = URL.createObjectURL(file)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = file.name
  link.style.display = 'none'

  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)

  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 10000)
}

export function RecoverList({ addEndSeparator }: { addEndSeparator: boolean }) {
  const { t } = useTranslation(['recordings', 'shared'])
  const [openDropdownId, setOpenDropdownId] = useState<string | null>(null)
  const recordingsById = useLocalRecordingsStore(
    (state) => state.recordingsById
  )
  const queuedRecordings = useMemo(
    () =>
      Object.values(recordingsById)
        .filter(
          (recording) =>
            (recording.status === 'stopped' ||
              recording.status === 'uploading' ||
              recording.status === 'exited' ||
              recording.status === 'upload_failed') &&
            recording.chunkCount > 0
        )
        .sort((a, b) => b.updatedAt - a.updatedAt),
    [recordingsById]
  )

  if (queuedRecordings.length === 0) {
    return null
  }

  return (
    <section
      className="recordings-recovery-alert"
      aria-label={t('recordings:localQueue.title')}
    >
      <div className="recordings-recovery-alert__list" role="list">
        {queuedRecordings.map((recording, recordingIdx) => {
          const isUploading = recording.status === 'uploading'
          const isPendingUpload = isUploading || recording.status === 'stopped'
          const isFailed =
            recording.status === 'upload_failed' ||
            recording.status === 'exited'

          const tooltipLabel =
            recording.status === 'upload_failed'
              ? t('recordings:localQueue.tooltip.failedToUpload')
              : recording.status === 'exited'
                ? t('recordings:localQueue.tooltip.interrupted')
                : 'Unknown error'

          return (
            <Fragment key={recording.id}>
              {recordingIdx > 0 && <HorizontalSeparator withPadding={false} />}
              <article
                className="recordings-recovery-alert__item"
                role="listitem"
              >
                <div className="recordings-recovery-alert__item-left">
                  <div className="recordings-recovery-alert__item-status">
                    {isUploading ? (
                      <CircularProgress
                        progress={recording.uploadProgress}
                        status={'uploading'}
                      />
                    ) : isPendingUpload ? (
                      <span
                        role="status"
                        aria-label={t(
                          'recordings:transcript.statusPreview.pending'
                        )}
                      >
                        <Spinner />
                      </span>
                    ) : (
                      <Tooltip content={tooltipLabel}>
                        <span
                          role="img"
                          aria-label={tooltipLabel}
                          className="warning"
                        >
                          <Warning />
                        </span>
                      </Tooltip>
                    )}
                  </div>
                  <div className="recordings-recovery-alert__item-info">
                    <div className="recordings-recovery-alert__item-title-row">
                      <span className="recordings-recovery-alert__item-title">
                        {t('recordings:localQueue.recordingLabel', {
                          value: recording.createdAt,
                        })}
                      </span>
                    </div>
                    <div className="recordings-recovery-alert__item-meta">
                      <span>
                        {t('shared:utils.duration', {
                          duration: intervalToDuration({
                            start: 0,
                            end: Math.max(recording.durationMs, 1000),
                          }),
                        })}
                      </span>
                      <span>•</span>
                      <span>
                        {t('shared:utils.formatDateTime', {
                          value: recording.createdAt,
                        })}
                      </span>
                    </div>
                  </div>
                </div>
                <div className="recordings-recovery-alert__actions">
                  {isFailed && (
                    <>
                      <Button
                        size="small"
                        variant="tertiary"
                        color="neutral"
                        disabled={isUploading}
                        aria-label={t(
                          'recordings:localQueue.actions.retryAriaLabel'
                        )}
                        onClick={() =>
                          useLocalRecordingsStore
                            .getState()
                            .requestUpload(recording.id)
                        }
                        icon={<Retry size="small" />}
                      >
                        {t('recordings:localQueue.actions.retry')}
                      </Button>
                      <DropdownMenu
                        isOpen={openDropdownId === recording.id}
                        onOpenChange={(open) =>
                          setOpenDropdownId(open ? recording.id : null)
                        }
                        options={[
                          {
                            label: t('recordings:localQueue.actions.download'),
                            icon: <Download size="small" />,
                            callback: () => {
                              setOpenDropdownId(null)
                              createLocalFileFromChunkStore(recording.id).then(
                                downloadFile
                              )
                            },
                          },
                          {
                            label: t('recordings:localQueue.actions.discard'),
                            icon: <Trash size="small" />,
                            callback: () => {
                              const shouldDiscard = window.confirm(
                                t('recordings:localQueue.confirmDiscard')
                              )
                              if (!shouldDiscard) {
                                return
                              }
                              setOpenDropdownId(null)
                              useLocalRecordingsStore
                                .getState()
                                .removeRecording(recording.id)
                            },
                          },
                        ]}
                      >
                        <Button
                          size="small"
                          variant="tertiary"
                          color="neutral"
                          disabled={isUploading}
                          onClick={() =>
                            setOpenDropdownId(
                              openDropdownId === recording.id
                                ? null
                                : recording.id
                            )
                          }
                          aria-label={t('actions.moreOptionsAriaLabel', {
                            title: t('recordings:localQueue.recordingLabel', {
                              value: recording.createdAt,
                            }),
                          })}
                          icon={
                            <span
                              className="material-icons more"
                              aria-hidden="true"
                            >
                              more_horiz
                            </span>
                          }
                        />
                      </DropdownMenu>
                    </>
                  )}
                </div>
              </article>
            </Fragment>
          )
        })}
      </div>
      {addEndSeparator && (
        <div className="recordings-recovery-alert__list__end-separator">
          <HorizontalSeparator withPadding={false} />
        </div>
      )}
    </section>
  )
}
