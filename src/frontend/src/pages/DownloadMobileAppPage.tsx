import { BaseLayout } from '@/layout/BaseLayout'
import { useTranslation } from 'react-i18next'
import { DownloadAppsButtons } from '@/components/DownloadAppsButtons'

export default function DownloadMobileAppPage() {
  const { t } = useTranslation('layout')

  return (
    <BaseLayout showShowcaseAssistant={false}>
      <div className="download-mobile-app-page">
        <img src="/public/assets/logo-download.svg" alt="Download mobile app" />
        <span>{t('info.mobileApp.catchPhrase')}</span>
        <DownloadAppsButtons />
      </div>
    </BaseLayout>
  )
}
