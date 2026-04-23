import { QRCodeSVG } from 'qrcode.react'
import { apiUrl } from '@/api/apiUrl'
import { useMemo } from 'react'
import { useConfig } from '@/api/useConfig'
import clsx from 'clsx'
import { Button } from '@gouvfr-lasuite/cunningham-react'
import { XMark } from '@gouvfr-lasuite/ui-kit'
import { useTranslation } from 'react-i18next'

export function DownloadMobileAppPopUp({
  open,
  setOpen,
}: {
  open: boolean
  setOpen: (open: boolean) => void
}) {
  const { t } = useTranslation('layout')
  const scanUrl = useMemo(() => {
    return apiUrl('/download-mobile-app')
  }, [])
  const { data } = useConfig()

  return (
    <div className={clsx('download-mobile-app-pop-up', !open && 'hidden')}>
      <Button
        className="download-mobile-app-pop-up__close-button"
        icon={<XMark />}
        aria-label={'Close the mobile app download pop-up'}
        size="nano"
        variant="tertiary"
        color="neutral"
        onClick={() => setOpen(false)}
      />
      <div className="download-mobile-app-pop-up__intro">
        <span>{t('info.mobileApp.title')}</span>
        <span>{t('info.mobileApp.description')}</span>
      </div>
      <div className="download-mobile-app-pop-up__qr-code-container">
        <a href={scanUrl} target="_blank" rel="noreferrer">
          <QRCodeSVG value={scanUrl} />
        </a>
        <span>{t('info.mobileApp.scanToInstall')}</span>
        <div className="download-mobile-app-pop-up__download-links">
          <a href={data?.mobile_app?.ios_download_link} target="_blank">
            <img alt="Apple Logo" src="/assets/files/icons/apple-logo.svg" />
          </a>
          <a href={data?.mobile_app?.android_download_link} target="_blank">
            <img
              alt="Play store Logo"
              src="/assets/files/icons/play-store-logo.svg"
            />
          </a>
        </div>
      </div>
    </div>
  )
}
