import { useConfig } from '@/api/useConfig'
import { useTranslation } from 'react-i18next'
import { useMemo } from 'react'

export function DownloadAppsButtons() {
  const { data } = useConfig()

  const { i18n } = useTranslation('layout')
  const language = useMemo(
    () => i18n.language.slice(0, 2).toLowerCase(),
    [i18n.language]
  )

  // we should remove this once the store are live to avoid moving elements
  if (
    !data?.mobile_app?.ios_download_link ||
    !data?.mobile_app?.android_download_link
  )
    return null

  return (
    <div className="download-apps-buttons">
      <a href={data?.mobile_app?.ios_download_link}>
        <img
          height={44}
          alt="Download on the App Store"
          src={`/assets/download-app-store-${language}.svg`}
        />
      </a>
      <a href={data?.mobile_app?.android_download_link}>
        <img
          height={44}
          alt="Download on the Google Play Store"
          src={`/assets/download-play-store-${language}.svg`}
        />
      </a>
    </div>
  )
}
