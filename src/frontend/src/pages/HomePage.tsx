import { useTranslation } from 'react-i18next'
import { authUrl, useUser } from '@/features/auth'
import { Hero, ProConnectButton, Spinner } from '@gouvfr-lasuite/ui-kit'
import LogoApp from '@/layout/LogoApp'
import { useConfig } from '@/api/useConfig'
import { Button } from '@gouvfr-lasuite/cunningham-react'
import { Redirect } from 'wouter'

export function HomePage() {
  const { t } = useTranslation('home')
  const { isLoggedIn, isLoading } = useUser()

  const { data: appConfig } = useConfig()

  if (isLoading) return <Spinner />

  if (!isLoggedIn) {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh',
        }}
      >
        <Hero
          banner="/assets/hero-beta.png"
          title={t('title')}
          subtitle={t('subtitle')}
          logo={<LogoApp height={42} />}
          mainButton={
            appConfig?.use_proconnect_button ? (
              <ProConnectButton
                onClick={() => window.location.replace(authUrl())}
              />
            ) : (
              <Button onClick={() => window.location.replace(authUrl())}>
                {t('login')}
              </Button>
            )
          }
        />
      </div>
    )
  }

  return <Redirect to="/recordings" />
}
