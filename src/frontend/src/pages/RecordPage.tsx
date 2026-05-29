import ConnectedLayout from '@/layout/ConnectedLayout.tsx'
import RecordComponent from '@/features/recordings/components/RecordComponent.tsx'
import { useTranslation } from 'react-i18next'

export default function RecordPage() {
  const { t } = useTranslation('layout')
  return (
    <ConnectedLayout
      className="record-parent"
      pageTitle={t('pageTitles.record')}
    >
      <RecordComponent />
    </ConnectedLayout>
  )
}
