import ConnectedLayout from '@/layout/ConnectedLayout.tsx'
import RecordComponent from '@/features/recordings/components/RecordComponent.tsx'
import { useTranslation } from 'react-i18next'
import { useState } from 'react'
import { Button, Modal, ModalSize } from '@gouvfr-lasuite/cunningham-react'
import { Download } from '@gouvfr-lasuite/ui-kit/icons'
import { useLocation } from 'wouter'

const isMobile =
  // @ts-expect-error Not supported by TypeScript
  navigator.userAgentData?.mobile ??
  /Android|iPhone|iPad|iPod/i.test(navigator.userAgent)

export default function RecordPage() {
  const { t } = useTranslation(['layout', 'record'])
  const [showMobileRecordingAlert, setShowMobileRecordingAlert] =
    useState(isMobile)
  const [, navigate] = useLocation()

  return (
    <ConnectedLayout
      className="record-parent fancy-background"
      pageTitle={t('pageTitles.record')}
      readonly
    >
      <h1 className="sr-only">{t('recordPageH1')}</h1>
      {!showMobileRecordingAlert && <RecordComponent />}
      <Modal
        size={ModalSize.MEDIUM}
        isOpen={showMobileRecordingAlert}
        onClose={() => setShowMobileRecordingAlert(false)}
        closeOnClickOutside={true}
        title={t('record:mobileAlert.title')}
        rightActions={
          <>
            <Button
              onClick={() => {
                navigate('/download-mobile-app')
              }}
              icon={<Download />}
              className="btn-centered"
            >
              {t('record:mobileAlert.downloadApp')}
            </Button>
            <Button
              onClick={() => {
                setShowMobileRecordingAlert(false)
              }}
              variant="bordered"
              color="neutral"
              className="btn-centered"
            >
              {t('record:mobileAlert.continueAnyways')}
            </Button>
          </>
        }
      >
        <p>{t('record:mobileAlert.description')}</p>
      </Modal>
    </ConnectedLayout>
  )
}
