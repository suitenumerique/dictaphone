import { MainLayout, Spinner } from '@gouvfr-lasuite/ui-kit'
import LogoApp from '@/layout/LogoApp.tsx'
import { HeaderRight } from '@/layout/HeaderRight.tsx'
import { useUser } from '@/features/auth'
import { Link, Redirect } from 'wouter'
import { useTranslation } from 'react-i18next'
import clsx from 'clsx'
import { HelpMenu } from '@/layout/HelpMenu'

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
      hideLeftPanelOnDesktop={true}
      icon={
        <Link
          to="/recordings"
          aria-label={t('home')}
          style={{ textDecoration: 'none' }}
        >
          <LogoApp variant="multiline" height={42} />
        </Link>
      }
      rightHeaderContent={<HeaderRight />}
      isLeftPanelOpen={false}
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
      <div className="dictaphone__connected_layout_help_menu">
        <HelpMenu />
      </div>
    </MainLayout>
  )
}
