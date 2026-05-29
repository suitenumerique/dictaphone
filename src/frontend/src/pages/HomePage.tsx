import { useTranslation } from 'react-i18next'
import { authUrl } from '@/features/auth/utils/authUrl'
import { useUser } from '@/features/auth/api/useUser'
import { Button } from '@gouvfr-lasuite/cunningham-react'
import { Redirect } from 'wouter'
import { BaseLayout } from '@/layout/BaseLayout'
import { DownloadAppsButtons } from '@/components/DownloadAppsButtons'

export default function HomePage() {
  const { t } = useTranslation(['home', 'layout'])

  const { isLoggedIn, isLoading } = useUser()

  if (isLoading) return <></>

  if (!isLoggedIn) {
    return (
      <BaseLayout
        className="home-page"
        showShowcaseAssistant={true}
        pageTitle={t('layout:pageTitles.home')}
      >
        <>
          <img
            className="home-page__app-logo"
            alt={t('images.appLogoAlt')}
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
            <img alt={t('images.heroAlt')} src="/assets/hero.svg" />
          </div>

          <div className="home-page__examples">
            <div className="home-page__examples__images">
              <img alt={t('images.example1Alt')} src="/assets/home/ex-1.svg" />
              <img alt={t('images.example2Alt')} src="/assets/home/ex-2.svg" />
              <img alt={t('images.example3Alt')} src="/assets/home/ex-3.svg" />
            </div>
            <DownloadAppsButtons />
          </div>
        </>
      </BaseLayout>
    )
  }

  return <Redirect to="/recordings" />
}
