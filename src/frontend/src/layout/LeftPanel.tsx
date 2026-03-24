import { HorizontalSeparator } from '@gouvfr-lasuite/ui-kit'
import { useUser } from '@/features/auth'
import { LanguagePickerSyncedBackend } from '@/layout/HeaderRight.tsx'
import { Button } from '@gouvfr-lasuite/cunningham-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'wouter'

export default function LeftPanel() {
  const { logout } = useUser()
  const { t } = useTranslation('layout')

  return (
    <nav className="dictaphone__left-panel">
      <div className="dictaphone__left-panel-header">
        {/*<div className="dictaphone__left-panel-header-content">*/}

        {/*</div>*/}
        {/*<HorizontalSeparator withPadding={false} />*/}
      </div>
      <div className="dictaphone__left-panel-content">
        <Link
          to="/recordings"
          className={(active) =>
            active ? 'c__breadcrumbs__button active' : 'c__breadcrumbs__button'
          }
        >
          <span className="material-icons">record_voice_over</span>
          {t('breadcrumbs.myRecordings')}
        </Link>
        <Link
          to="/trash"
          className={(active) =>
            active ? 'c__breadcrumbs__button active' : 'c__breadcrumbs__button'
          }
        >
          <span className="material-icons">delete</span>
          {t('breadcrumbs.trash')}
        </Link>
      </div>
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
