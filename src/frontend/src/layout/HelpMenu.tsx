import { DropdownMenu, Info, QuestionMark } from '@gouvfr-lasuite/ui-kit'
import { Button } from '@gouvfr-lasuite/cunningham-react'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useUser } from '@/features/auth'
import { DownloadMobileAppPopUp } from '@/layout/DownloadMobileAppPopUp'
import { useConfig } from '@/api/useConfig'

export function HelpMenu() {
  const [isOpen, setIsOpen] = useState(false)
  const [openDownloadMobileAppPopUp, setOpenDownloadMobileAppPopUp] =
    useState(false)
  const { t, i18n } = useTranslation('layout')
  const user = useUser()

  const { data } = useConfig()

  // we should remove this once the store are live to avoid moving elements
  const forceHideMobileStuff =
    !data?.mobile_app?.ios_download_link ||
    !data?.mobile_app?.android_download_link

  useEffect(() => {
    if (user.user?.flag_show_mobile_app_popup) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setOpenDownloadMobileAppPopUp(true)
    }
  }, [user.user?.flag_show_mobile_app_popup])

  useEffect(() => {
    if (isOpen) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setOpenDownloadMobileAppPopUp(false)
    }
  }, [isOpen])

  const handleCloseMobileAppPopup = useCallback(() => {
    if (user && user.updateUser && user.user?.flag_show_mobile_app_popup) {
      user.updateUser({ flag_show_mobile_app_popup: false })
    }
    setOpenDownloadMobileAppPopUp(false)
  }, [user])

  const handleSupportClick = useCallback(() => {
    const to = 'support-transcripts@numerique.gouv.fr'
    const subject = encodeURIComponent('Assistant Transcripts - Support')

    const info = [
      'Info:',
      `User: ${user.user?.id}`,
      `User agent: ${navigator.userAgent}`,
      `Language: ${i18n.language}`,
      `Platform: ${navigator.platform}`,
      `Screen: ${window.screen.width}x${window.screen.height}`,
      `Viewport: ${window.innerWidth}x${window.innerHeight}`,
    ].join('\n')

    const body = encodeURIComponent(t('info.supportEmailStart') + '\n\n' + info)

    window.location.href = `mailto:${to}?subject=${subject}&body=${body}`

    window.open('mailto:', '_blank')
  }, [i18n.language, t, user.user?.id])

  return (
    <>
      <DownloadMobileAppPopUp
        open={openDownloadMobileAppPopUp && !forceHideMobileStuff}
        setOpen={handleCloseMobileAppPopup}
      />
      <DropdownMenu
        options={[
          ...(forceHideMobileStuff
            ? []
            : [
                {
                  icon: <span className="material-icons">devices</span>,
                  label: t('info.help.mobileApp'),
                  callback: () => setOpenDownloadMobileAppPopUp(true),
                },
              ]),
          {
            icon: <span className="material-icons">article</span>,
            label: t('info.help.documentation'),
            callback: () => {
              window.open(t('info.documentationUrl'), '_blank')
            },
          },
          {
            icon: <Info />,
            label: t('info.help.support'),
            callback: handleSupportClick,
          },
        ]}
        variant="default"
        isOpen={isOpen}
        onOpenChange={setIsOpen}
      >
        <Button
          color="neutral"
          variant="tertiary"
          icon={<QuestionMark />}
          onClick={() => setIsOpen(true)}
        />
      </DropdownMenu>
    </>
  )
}
