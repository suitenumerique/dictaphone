import { BaseLayout } from '@/layout/BaseLayout'
import { useTranslation } from 'react-i18next'
import { DownloadAppsButtons } from '@/components/DownloadAppsButtons'

export default function DownloadMobileAppPage() {
  const { t } = useTranslation('layout')

  return (
    <BaseLayout
      showShowcaseAssistant={false}
      pageTitle={t('pageTitles.downloadMobileApp')}
    >
      <div className="download-mobile-app-page">
        <img src="/assets/logo-download.svg" alt="Download mobile app" />
        <span>{t('info.mobileApp.catchPhrase')}</span>
        <DownloadAppsButtons />
      </div>
    </BaseLayout>
  )
}
