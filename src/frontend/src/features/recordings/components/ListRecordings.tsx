import { useListMyFilesInfinite } from '@/features/files/api/listFiles.ts'
import { useTranslation } from 'react-i18next'
import { Spinner, useResponsive } from '@gouvfr-lasuite/ui-kit'
import { useLocation } from 'wouter'
import RecordComponent from '@/features/recordings/components/RecordComponent.tsx'
import { Button, Tooltip } from '@gouvfr-lasuite/cunningham-react'
import { intervalToDuration } from 'date-fns'
import { ApiFileItem } from '@/features/files/api/types.ts'
import { useMemo } from 'react'
import { getMainAiJobs } from '@/features/ai-jobs/utils/getMainAiJobs.ts'
import clsx from 'clsx'
import { FileActionMenu } from '@/features/recordings/components/FileActionMenu.tsx'

function HeaderAction() {
  const { t } = useTranslation('upload')
  const { isDesktop } = useResponsive()

  return (
    <>
      <Button
        aria-label={t('cta')}
        onClick={() => document.getElementById('import-files')?.click()}
        icon={<span className="material-icons">upload</span>}
        variant="secondary"
      >
        {isDesktop && <span>{t('cta')}</span>}
      </Button>
      <RecordComponent />
    </>
  )
}

function RecordingStatus({ recording }: { recording: ApiFileItem }) {
  const { t } = useTranslation('recordings')

  const { lastAiJobTranscript } = useMemo(
    () => getMainAiJobs(recording.ai_jobs),
    [recording.ai_jobs]
  )

  if (lastAiJobTranscript?.status === 'success') {
    return <img src="/assets/files/icons/doc.svg" alt="Document logo" />
  }

  if (lastAiJobTranscript?.status === 'failed') {
    return (
      <Tooltip content={t('transcript.status.failed')}>
        <span aria-hidden="true">⚠️</span>
      </Tooltip>
    )
  }
  return <Spinner />
}

export function ListRecordings({
  queryData,
  isDropZoneActive,
  isTrashPage = false,
}: {
  queryData: ReturnType<typeof useListMyFilesInfinite>
  isDropZoneActive: boolean
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
    <>
      <div
        className={clsx({
          'drop-zone--drag-in-progress-main-area':
            !isTrashPage && isDropZoneActive,
        })}
      >
        <HeaderAction />
      </div>
      {queryData.isPending && !queryData.data && <Spinner />}
      {queryData.error && <div>{t('errorFetching')}</div>}
      {queryData.data && totalFilesCount === 0 && (
        <div>{t(isTrashPage ? 'noRecordingsTrash' : 'noRecordings')}</div>
      )}
      {allFiles.length > 0 && (
        <div
          className="recordings-list"
          role="list"
          aria-label={t('list.title')}
        >
          {allFiles.map((file) => (
            <div
              className="recordings-list__item clickable"
              key={file.id}
              role="button"
              tabIndex={0}
              onClick={() => navigate(`/recordings/${file.id}`)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  navigate(`/recordings/${file.id}`)
                }
              }}
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
                          end: file.duration_seconds * 1000,
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

              {/* eslint-disable-next-line jsx-a11y/click-events-have-key-events,jsx-a11y/no-static-element-interactions */}
              <div onClick={(e) => e.stopPropagation()}>
                <FileActionMenu file={file} />
              </div>
            </div>
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
    </>
  )
}
