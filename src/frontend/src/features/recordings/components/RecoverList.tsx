import {
  createLocalFileFromChunkStore,
  useLocalRecordingsStore,
} from '@/features/recordings/store/useLocalRecordingsStore.ts'
import { Button } from '@gouvfr-lasuite/cunningham-react'
import { intervalToDuration } from 'date-fns'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Spinner } from '@gouvfr-lasuite/ui-kit'
import { ProgressBar } from '@/components/ProgressBar'

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

export function RecoverList() {
  const { t } = useTranslation(['recordings', 'shared'])
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
        {queuedRecordings.map((recording) => {
          const isUploading = recording.status === 'uploading'
          const isFailed =
            recording.status === 'upload_failed' ||
            recording.status === 'exited'

          const badgeLabel =
            recording.status === 'upload_failed'
              ? t('recordings:localQueue.badges.failedToUpload')
              : recording.status === 'exited'
                ? t('recordings:localQueue.badges.interrupted')
                : t('recordings:localQueue.badges.local')

          return (
            <article
              key={recording.id}
              className="recordings-recovery-alert__item"
            >
              <div className="recordings-recovery-alert__item-left">
                <div className="recordings-recovery-alert__item-status">
                  {recording.status === 'uploading' ? (
                    <Spinner />
                  ) : (
                    <span aria-hidden="true">⚠️</span>
                  )}
                </div>
                <div className="recordings-recovery-alert__item-info">
                  <div className="recordings-recovery-alert__item-title-row">
                    <span className="recordings-recovery-alert__item-title">
                      {t('recordings:localQueue.recordingLabel', {
                        value: recording.createdAt,
                      })}
                    </span>
                    <span className="recordings-recovery-alert__badge">
                      {badgeLabel}
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
              {isUploading && (
                <ProgressBar
                  // We avoid showing 100% before it's fully done
                  value={Math.min(recording.uploadProgress, 99)}
                  minValue={0}
                  maxValue={100}
                />
              )}
              <div className="recordings-recovery-alert__actions">
                {recording.status !== 'uploading' && (
                  <Button
                    color="neutral"
                    variant="bordered"
                    disabled={isUploading}
                    size="small"
                    aria-label={t('recordings:localQueue.actions.discard')}
                    onClick={() => {
                      const shouldDiscard = window.confirm(
                        t('recordings:localQueue.confirmDiscard')
                      )
                      if (!shouldDiscard) {
                        return
                      }
                      useLocalRecordingsStore
                        .getState()
                        .removeRecording(recording.id)
                    }}
                    icon={<span className="material-icons">delete</span>}
                  ></Button>
                )}
                {isFailed && (
                  <Button
                    color="neutral"
                    variant="secondary"
                    size="small"
                    disabled={isUploading}
                    onClick={async () => {
                      const file = await createLocalFileFromChunkStore(
                        recording.id
                      )
                      downloadFile(file)
                    }}
                    icon={<span className="material-icons">download</span>}
                  >
                    {t('recordings:localQueue.actions.download')}
                  </Button>
                )}

                {(recording.status === 'stopped' ||
                  isFailed ||
                  recording.status === 'exited') && (
                  <Button
                    color="brand"
                    size="small"
                    variant="secondary"
                    disabled={isUploading}
                    onClick={() =>
                      useLocalRecordingsStore
                        .getState()
                        .requestUpload(recording.id)
                    }
                    icon={<span className="material-icons">cloud_upload</span>}
                  >
                    {t(
                      isFailed
                        ? 'recordings:localQueue.actions.retry'
                        : 'recordings:localQueue.actions.upload'
                    )}
                  </Button>
                )}
              </div>
            </article>
          )
        })}
      </div>
    </section>
  )
}
