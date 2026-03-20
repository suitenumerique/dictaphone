import { HorizontalSeparator } from '@gouvfr-lasuite/ui-kit'
import { useUser } from '@/features/auth'
import { LanguagePickerSyncedBackend } from '@/layout/HeaderRight.tsx'
import { Button } from '@gouvfr-lasuite/cunningham-react'
import { useTranslation } from 'react-i18next'

export default function LeftPanel() {
  const { logout } = useUser()
  const { t } = useTranslation('layout')

  return (
    <nav className="dictaphone__left-panel">
      <div className="dictaphone__left-panel-header">Top</div>
      <div className="dictaphone__left-panel-content">Midel</div>
      <div className="dictaphone__left-panel-footer">
        <HorizontalSeparator withPadding={false} />
        <div className="dictaphone__left-panel-footer-content">
          <LanguagePickerSyncedBackend />
          <Button
            size="small"
            variant="tertiary"
            onClick={() => logout()}
            icon={<span className="material-icons">logout</span>}
          >
            {t('logout')}
          </Button>
        </div>
      </div>
    </nav>
  )
}
