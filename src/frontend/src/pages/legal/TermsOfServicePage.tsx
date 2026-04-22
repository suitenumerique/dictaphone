import { useTranslation } from 'react-i18next'
import { BaseLayout } from '@/layout/BaseLayout'
import { marked } from 'marked'
import { useMemo } from 'react'

export default function TermsOfServicePage() {
  const { t } = useTranslation('legals')

  const html = useMemo(() => {
    return marked
      .parse(t('termsOfService.content'), { async: false })
      .replace(/ :/g, '&nbsp;:')
  }, [t])

  return (
    <BaseLayout
      showShowcaseAssistant={false}
      className="legal-page"
      title={t('termsOfService.title')}
    >
      <section dangerouslySetInnerHTML={{ __html: html }}></section>
    </BaseLayout>
  )
}
