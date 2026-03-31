import { useListMyFiles } from '@/features/files/api/listFiles.ts'
import { useDeleteFile } from '@/features/files/api/deleteFile.ts'
import { useTranslation } from 'react-i18next'
import { Badge, Spinner } from '@gouvfr-lasuite/ui-kit'
import { Card } from '@/components/Card.tsx'
import { Pagination } from '@/components/Pagination.tsx'
import { useLocation } from 'wouter'
import RecordComponent from '@/features/recordings/components/RecordComponent.tsx'
import { Button } from '@gouvfr-lasuite/cunningham-react'
import { intervalToDuration } from 'date-fns'
import { ApiFileItem } from '@/features/files/api/types.ts'
import { ComponentProps, useMemo } from 'react'
import { getMainAiJobs } from '@/features/ai-jobs/utils/getMainAiJobs.ts'
import { ApiAiJob } from '@/features/ai-jobs/api/types.ts'
import clsx from 'clsx'

function HeaderAction() {
  const { t } = useTranslation('upload')
  return (
    <>
      <Button
        aria-label={t('cta')}
        onClick={() => document.getElementById('import-files')?.click()}
        icon={<span className="material-icons">upload</span>}
        variant="secondary"
      >
        <span className="recording-upload-bnt-label">{t('cta')}</span>
      </Button>
      <RecordComponent />
    </>
  )
}

const BADGE_TYPE_BY_STATUS: Record<
  ApiAiJob['status'],
  ComponentProps<typeof Badge>['type']
> = {
  pending: 'info',
  success: 'success',
  failed: 'danger',
}

function RecordingStatus({ recording }: { recording: ApiFileItem }) {
  const { t } = useTranslation('recordings')

  const { lastAiJobTranscript, lastAiJobSummary } = useMemo(
    () => getMainAiJobs(recording.ai_jobs),
    [recording.ai_jobs]
  )

  return (
    <div className="recording-status">
      {lastAiJobTranscript !== null && (
        <Badge type={BADGE_TYPE_BY_STATUS[lastAiJobTranscript.status]}>
          {t(`transcript.statusPreview.${lastAiJobTranscript.status}`)}
        </Badge>
      )}
      {lastAiJobSummary !== null && (
        <Badge type={BADGE_TYPE_BY_STATUS[lastAiJobSummary.status]}>
          {t(`summary.statusPreview.${lastAiJobSummary.status}`)}
        </Badge>
      )}
    </div>
  )
}

export default function ListRecordings({
  queryData,
  page,
  pageSize,
  onPageChange,
  isDropZoneActive
}: {
  queryData: ReturnType<typeof useListMyFiles>
  page: number
  pageSize: number
  onPageChange: (page: number) => void,
  isDropZoneActive: boolean,
}) {
  const [, navigate] = useLocation()
  const { t } = useTranslation('recordings')
  const deleteFileMutation = useDeleteFile()

  return (
    <Card
      title={t('list.title')}
      action={<HeaderAction />}
      className={clsx({
        'drop-zone--drag-in-progress-main-area': isDropZoneActive,
      })}
    >
      {queryData.isPending && !queryData.data && <Spinner />}
      {queryData.error && <div>{t('errorFetching')}</div>}
      {queryData.data && queryData.data.count === 0 && (
        <div>{t('noRecordings')}</div>
      )}
      {queryData.data && queryData.data.count > 0 && (
        <div className="recordings-list">
          <table
            className="recordings-list__table"
            aria-label={t('list.ariaLabelTable')}
          >
            <thead>
              <tr>
                <th scope="col">{t('list.columns.title')}</th>
                <th scope="col">{t('list.columns.duration')}</th>
                <th scope="col">{t('list.columns.processes')}</th>
                <th scope="col">{t('list.columns.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {queryData.data.results.map((file) => {
                const isDeletingCurrentFile =
                  deleteFileMutation.isPending &&
                  deleteFileMutation.variables?.fileId === file.id
                return (
                  <tr
                    className="clickable"
                    key={file.id}
                    onClick={() => navigate(`/recordings/${file.id}`)}
                  >
                    <td>{file.title || file.filename}</td>
                    <td>
                      {t('duration', {
                        duration: intervalToDuration({
                          start: 0,
                          end: file.duration_seconds * 1000,
                        }),
                      })}
                    </td>
                    <td>
                      <RecordingStatus recording={file} />
                    </td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        className="recordings-list__delete-button"
                        aria-label={t('list.deleteAriaLabel', {
                          title: file.title || file.filename,
                        })}
                        onClick={() =>
                          deleteFileMutation.mutate({ fileId: file.id })
                        }
                        disabled={isDeletingCurrentFile}
                      >
                        <span className="material-icons" aria-hidden="true">
                          delete
                        </span>
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <Pagination
            page={page}
            pageSize={pageSize}
            totalItems={queryData.data.count}
            onPageChange={onPageChange}
            ariaLabel={t('list.paginationAriaLabel')}
            previousAriaLabel={t('list.paginationPreviousAriaLabel')}
            nextAriaLabel={t('list.paginationNextAriaLabel')}
          />
        </div>
      )}
    </Card>
  )
}
