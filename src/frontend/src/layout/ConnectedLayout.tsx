import { MainLayout } from '@gouvfr-lasuite/ui-kit'
import LogoApp from '@/layout/LogoApp.tsx'
import { HeaderRight } from '@/layout/HeaderRight.tsx'
import { useUser } from '@/features/auth'
import { Redirect } from 'wouter'

export default function ConnectedLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const user = useUser()
  if (!user.isLoggedIn) {
    return <Redirect to="/" />
  }

  return (
    <MainLayout
      icon={<LogoApp withLabel />}
      hideLeftPanelOnDesktop={true}
      rightHeaderContent={<HeaderRight />}
    >
      <div className="dictaphone__connected_layout_container">
        <main className="dictaphone__connected_layout_content">{children}</main>
      </div>
    </MainLayout>
  )
}
