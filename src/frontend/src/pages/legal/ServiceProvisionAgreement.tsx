import { useTranslation } from 'react-i18next'
import { BaseLayout } from '@/layout/BaseLayout'
import { marked } from 'marked'
import { useMemo } from 'react'

export default function ServiceProvisionAgreementPage() {
  const { t } = useTranslation('legals')

  const html = useMemo(() => {
    return marked
      .parse(t('serviceProvisionAgreement.content'), { async: false })
      .replace(/ :/g, '&nbsp;:')
  }, [t])

  return (
    <BaseLayout
      showShowcaseAssistant={false}
      className="legal-page"
      heading={t('serviceProvisionAgreement.title')}
      pageTitle={t('serviceProvisionAgreement.title')}
    >
      <section dangerouslySetInnerHTML={{ __html: html }}></section>
    </BaseLayout>
  )
}
