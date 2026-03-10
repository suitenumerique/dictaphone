import { useTranslation } from 'react-i18next'
import { authUrl, useUser } from '@/features/auth'
import {
  Hero,
  MainLayout,
  ProConnectButton,
  Spinner,
} from '@gouvfr-lasuite/ui-kit'
import LogoApp from '@/layout/LogoApp'
import { HeaderRight } from '@/layout/HeaderRight'
import { useConfig } from '@/api/useConfig'
import { Button } from '@gouvfr-lasuite/cunningham-react'

export const Home = () => {
  const { t } = useTranslation('home')
  const config = useConfig()
  const { isLoggedIn, isLoading } = useUser()

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
          logo={<LogoApp size={100} />}
          mainButton={
            config.data?.use_proconnect_button ? (
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

  return (
    <MainLayout
      icon={<LogoApp />}
      hideLeftPanelOnDesktop={true}
      rightHeaderContent={<HeaderRight />}
    />
  )
}
