import { useConfig } from '@/api/useConfig'
import { useTranslation } from 'react-i18next'
import { useMemo } from 'react'

export function DownloadAppsButtons() {
  const { data } = useConfig()

  const { i18n, t } = useTranslation('layout')
  const language = useMemo(
    () => i18n.language.slice(0, 2).toLowerCase(),
    [i18n.language]
  )

  return (
    <div className="download-apps-buttons">
      <a
        href={data?.mobile_app?.ios_download_link}
        aria-label={t('images.downloadIosAriaLabel')}
      >
        <img
          height={44}
          alt={t('images.downloadIosAlt')}
          src={`/assets/download-app-store-${language}.svg`}
        />
      </a>
      <a
        href={data?.mobile_app?.android_download_link}
        aria-label={t('images.downloadAndroidAriaLabel')}
      >
        <img
          height={44}
          alt={t('images.downloadAndroidAlt')}
          src={`/assets/download-play-store-${language}.svg`}
        />
      </a>
    </div>
  )
}
