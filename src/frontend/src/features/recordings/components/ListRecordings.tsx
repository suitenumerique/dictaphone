import { useListMyFiles } from '@/features/files/api/listFiles.ts'
import { useDeleteFile } from '@/features/files/api/deleteFile.ts'
import { useTranslation } from 'react-i18next'
import { Spinner } from '@gouvfr-lasuite/ui-kit'
import { Card } from '@/components/Card.tsx'
import { Pagination } from '@/components/Pagination.tsx'
import { useLocation } from 'wouter'
import RecordComponent from '@/features/recordings/components/RecordComponent.tsx'
import { Button } from '@gouvfr-lasuite/cunningham-react'

const toMockDuration = ({ id, size }: { id: string; size: number }) => {
  const seed = [...id.replace(/-/g, '')].reduce((sum, value) => {
    return sum + value.charCodeAt(0)
  }, 0)
  const totalSeconds = 30 + ((seed + size) % 971)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes.toString().padStart(2, '0')}:${seconds
    .toString()
    .padStart(2, '0')}`
}

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

export default function ListRecordings({
  queryData,
  page,
  pageSize,
  onPageChange,
}: {
  queryData: ReturnType<typeof useListMyFiles>
  page: number
  pageSize: number
  onPageChange: (page: number) => void
}) {
  const [, navigate] = useLocation()
  const { t } = useTranslation('recordings')
  const deleteFileMutation = useDeleteFile()

  if (queryData.isPending && !queryData.data) {
    return <Spinner />
  }

  if (!queryData.data) {
    return <div>{t('errorFetching')}</div>
  }

  if (queryData.data?.count === 0) {
    return (
      <Card title={t('list.title')} action={<HeaderAction />}>
        <div>{t('noRecordings')}</div>
      </Card>
    )
  }

  return (
    <Card title={t('list.title')} action={<HeaderAction />}>
      <div className="recordings-list">
        <table
          className="recordings-list__table"
          aria-label={t('list.ariaLabelTable')}
        >
          <thead>
            <tr>
              <th scope="col">{t('list.columns.title')}</th>
              <th scope="col">{t('list.columns.duration')}</th>
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
                  key={file.id}
                  onClick={() => navigate(`/recordings/${file.id}`)}
                >
                  <td>{file.title || file.filename}</td>
                  <td>{toMockDuration(file)}</td>
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
    </Card>
  )
}
