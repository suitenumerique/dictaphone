import { Alert, Button, VariantType } from '@gouvfr-lasuite/ui-components'
import { QuestionMark } from '@gouvfr-lasuite/ui-components/icons'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Redirect } from 'wouter'
import { useConfig } from '@/api/useConfig'
import { BaseLayout } from '@/layout/BaseLayout'
import './RestrictedPage.scss'

function getRestrictedAccessMessage(
  messages: Record<string, string> | undefined,
  language: string
): string | undefined {
  const normalize = (locale: string) =>
    locale.replaceAll('_', '-').toLowerCase()
  const localized = Object.fromEntries(
    Object.entries(messages ?? {}).map(([locale, message]) => [
      normalize(locale),
      message,
    ])
  )
  const locale = normalize(language)
  for (const candidate of [locale, locale.split('-')[0]]) {
    const message = localized[candidate]
    if (typeof message === 'string' && message.trim()) return message
  }
  return undefined
}

export default function RestrictedPage() {
  const [fromBackend] = useState(
    () =>
      new URLSearchParams(window.location.search).get('access_denied') === '1'
  )

  useEffect(() => {
    if (!fromBackend) return
    const url = new URL(window.location.href)
    url.searchParams.delete('access_denied')
    window.history.replaceState(
      window.history.state,
      '',
      url.pathname + url.search + url.hash
    )
  }, [fromBackend])

  const { t, i18n } = useTranslation('shared')
  const { data: config } = useConfig()
  const message =
    getRestrictedAccessMessage(
      config?.restricted_access_message,
      i18n.resolvedLanguage ?? i18n.language
    ) ?? t('restricted.defaultMessage')

  if (!fromBackend) return <Redirect to="/" replace />

  return (
    <BaseLayout
      className="restricted-page"
      showShowcaseAssistant={false}
      pageTitle={t('restricted.title')}
    >
      <div className="restricted-page__content">
        <h1>{t('restricted.title')}</h1>
        <Alert
          type={VariantType.WARNING}
          canClose={false}
          buttons={
            config?.restricted_access_documentation_url && (
              <Button
                color="neutral"
                variant="tertiary"
                icon={<QuestionMark />}
                aria-label={t('restricted.documentation')}
                title={t('restricted.documentation')}
                href={config.restricted_access_documentation_url}
                target="_blank"
                rel="noopener noreferrer"
              />
            )
          }
        >
          <span className="restricted-page__message">{message}</span>
        </Alert>
        <div className="restricted-page__actions">
          <Button href="/">{t('restricted.home')}</Button>
        </div>
      </div>
    </BaseLayout>
  )
}
