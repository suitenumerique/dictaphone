import { useListMyFiles } from '@/features/files/api/listFiles.ts'
import { useTranslation } from 'react-i18next'
import { Spinner } from '@gouvfr-lasuite/ui-kit'

export default function ListRecordings({
  queryData,
}: {
  queryData: ReturnType<typeof useListMyFiles>
}) {
  const { t } = useTranslation('recordings')

  if (queryData.isPending) {
    return <Spinner />
  }

  if (!queryData.data) {
    return <div>{t('errorFetching')}</div>
  }

  if (queryData.data?.count === 0) {
    return <div>{t('noRecordings')}</div>
  }

  return null
}
