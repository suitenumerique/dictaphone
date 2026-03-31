import { MainLayout, Spinner } from '@gouvfr-lasuite/ui-kit'
import LogoApp from '@/layout/LogoApp.tsx'
import { HeaderRight } from '@/layout/HeaderRight.tsx'
import { useUser } from '@/features/auth'
import { Link, Redirect } from 'wouter'
import LeftPanel from '@/layout/LeftPanel.tsx'
import { useTranslation } from 'react-i18next'
import clsx from 'clsx'

export default function ConnectedLayout({
  children,
  ...rest
}: {
  children: React.ReactNode
  className?: string
}) {
  const { t } = useTranslation('layout')
  const user = useUser()

  if (user.isLoading) {
    return <Spinner />
  }

  if (!user.isLoggedIn) {
    return <Redirect to="/" />
  }

  return (
    <MainLayout
      icon={
        <Link
          to="/recordings"
          aria-label={t('home')}
          style={{ textDecoration: 'none' }}
        >
          <LogoApp withLabel />
        </Link>
      }
      rightHeaderContent={<HeaderRight />}
      leftPanelContent={<LeftPanel />}
    >
      <div
        {...rest}
        className={clsx(
          'dictaphone__connected_layout_container',
          rest.className
        )}
      >
        <main className="dictaphone__connected_layout_content">{children}</main>
      </div>
    </MainLayout>
  )
}
