import { useTranslation } from 'react-i18next'
import { Link } from 'wouter'
import { useUploadLimit } from '../api/uploadLimit'

export function UploadLimitAlert({
  linkToRecordings = false,
}: {
  linkToRecordings?: boolean
}) {
  const { t } = useTranslation('upload')
  const { data } = useUploadLimit()
  if (!data || data.limit === null || data.count < data.limit) return null

  return (
    <div className="limit-alert" role="alert">
      <strong>{t('fileLimit.title')}</strong>
      <p>{t('fileLimit.description', { limit: data.limit })}</p>
      {linkToRecordings && (
        <Link to="/recordings">{t('fileLimit.manageRecordings')}</Link>
      )}
    </div>
  )
}
