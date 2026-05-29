import { useListMyFilesInfinite } from '@/features/files/api/listFiles.ts'
import { useTranslation } from 'react-i18next'
import { Spinner, Warning } from '@gouvfr-lasuite/ui-kit'
import { useLocation } from 'wouter'
import { Button, Tooltip } from '@gouvfr-lasuite/cunningham-react'
import { intervalToDuration } from 'date-fns'
import { ApiFileItem } from '@/features/files/api/types.ts'
import { useMemo } from 'react'
import { getMainAiJobs } from '@/features/ai-jobs/utils/getMainAiJobs.ts'
import { FileActionMenu } from '@/features/recordings/components/FileActionMenu.tsx'

function RecordingStatus({ recording }: { recording: ApiFileItem }) {
  const { t } = useTranslation('recordings')

  const { lastAiJobTranscript } = useMemo(
    () => getMainAiJobs(recording.ai_jobs),
    [recording.ai_jobs]
  )

  if (lastAiJobTranscript?.status === 'success') {
    return (
      <div className="recordings-list__document-icon">
        <img
          src="/assets/files/icons/doc.svg"
          alt={t('transcript.statusPreview.success')}
        />
      </div>
    )
  }

  if (lastAiJobTranscript?.status === 'failed') {
    return (
      <Tooltip content={t('transcript.status.failed')}>
        <span
          role="img"
          aria-label={t('transcript.statusPreview.failed')}
          className="warning"
        >
          <Warning />
        </span>
      </Tooltip>
    )
  }
  return (
    <span role="status" aria-label={t('transcript.statusPreview.pending')}>
      <Spinner />
    </span>
  )
}

export function ListRecordings({
  queryData,
  isTrashPage = false,
}: {
  queryData: ReturnType<typeof useListMyFilesInfinite>
  isTrashPage?: boolean
}) {
  const [, navigate] = useLocation()
  const { t } = useTranslation(['recordings', 'shared'])

  const allFiles = useMemo(
    () => queryData.data?.pages.flatMap((page) => page.results) ?? [],
    [queryData.data]
  )
  const totalFilesCount = queryData.data?.pages[0]?.count ?? 0

  return (
    <section aria-label={t('mySavedRecordings')}>
      {queryData.isPending && !queryData.data && <Spinner />}
      {queryData.error && (
        <div className="subtle-info">{t('errorFetching')}</div>
      )}
      {queryData.data && totalFilesCount === 0 && (
        <div className="subtle-info">
          {t(isTrashPage ? 'noRecordingsTrash' : 'noRecordings')}
        </div>
      )}
      {allFiles.length > 0 && (
        <div
          className="recordings-list"
          role="list"
          aria-label={t('list.title')}
        >
          {allFiles.map((file) => (
            <article
              className="recordings-list__item"
              key={file.id}
              role="listitem"
            >
              <button
                className="recordings-list__item__open"
                onClick={() => navigate(`/recordings/${file.id}`)}
                aria-label={t('list.openRecording', {
                  title: file.title || file.filename,
                })}
              >
                <div className="recordings-list__item__left">
                  <div className="recordings-list__item__status">
                    <RecordingStatus recording={file} />
                  </div>
                  <div className="recordings-list__item__info">
                    <span className="recordings-list__item__title">
                      {file.title || file.filename}
                    </span>
                    <div className="recordings-list__item__metadata">
                      <span>
                        {t('shared:utils.duration', {
                          duration: intervalToDuration({
                            start: 0,
                            end: Math.max(file.duration_seconds || 1, 1) * 1000,
                          }),
                        })}
                      </span>
                      •
                      <span>
                        {t('shared:utils.formatDateTime', {
                          value: file.created_at,
                        })}
                      </span>
                    </div>
                  </div>
                </div>
              </button>
              <div
                className="recordings-list__item__actions"
                aria-label={t('actions.moreOptionsAriaLabel', {
                  title: file.title || file.filename,
                })}
              >
                <FileActionMenu file={file} />
              </div>
            </article>
          ))}

          {queryData.hasNextPage && (
            <div className="recordings-list__footer">
              <Button
                variant="secondary"
                onClick={() => queryData.fetchNextPage()}
                disabled={queryData.isFetchingNextPage}
              >
                {t(
                  queryData.isFetchingNextPage
                    ? 'list.loadingMore'
                    : 'list.loadMore'
                )}
              </Button>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
