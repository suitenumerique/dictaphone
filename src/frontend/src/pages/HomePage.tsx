import { useTranslation } from 'react-i18next'
import { authUrl, useUser } from '@/features/auth'
import { Button } from '@gouvfr-lasuite/cunningham-react'
import { Redirect } from 'wouter'
import { BaseLayout } from '@/layout/BaseLayout'
import { DownloadAppsButtons } from '@/components/DownloadAppsButtons'

export default function HomePage() {
  const { t } = useTranslation('home')

  const { isLoggedIn, isLoading } = useUser()

  if (isLoading) return <></>

  if (!isLoggedIn) {
    return (
      <BaseLayout className="home-page" showShowcaseAssistant={true}>
        <>
          <img
            className="home-page__app-logo"
            alt="L'assistant transcript logo"
            src="/assets/logo-single-line.svg"
          />
          <div className="home-page__hero">
            <div className="home-page__hero__intro">
              <h1>{t('title')}</h1>
              <p>{t('subtitle')}</p>

              <div className="home-page__hero__intro__buttons">
                <Button onClick={() => window.location.replace(authUrl())}>
                  {t('login')}
                </Button>
                <Button
                  variant="bordered"
                  href="https://assistant.numerique.gouv.fr/"
                  target="_blank"
                >
                  {t('discoverAssistant')}
                </Button>
              </div>
            </div>
            <img alt="Hero Transcripts" src="/assets/hero.svg" />
          </div>

          <div className="home-page__examples">
            <div className="home-page__examples__images">
              <img alt="Example app 1" src="/assets/home/ex-1.svg" />
              <img alt="Example app 2" src="/assets/home/ex-2.svg" />
              <img alt="Example app 3" src="/assets/home/ex-3.svg" />
            </div>
            <DownloadAppsButtons />
          </div>
        </>
      </BaseLayout>
    )
  }

  return <Redirect to="/recordings" />
}
