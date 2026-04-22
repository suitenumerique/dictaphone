import { useTranslation } from 'react-i18next'
import { BaseLayout } from '@/layout/BaseLayout'
import { useMemo } from 'react'
import { marked } from 'marked'

export default function PersonalDataPage() {
  const { t } = useTranslation('legals')

  const html = useMemo(() => {
    return marked
      .parse(t('personalData.content'), { async: false })
      .replace(/ :/g, '&nbsp;:')
  }, [t])

  return (
    <BaseLayout
      showShowcaseAssistant={false}
      className="legal-page"
      title={t('personalData.title')}
    >
      <section dangerouslySetInnerHTML={{ __html: html }}></section>
    </BaseLayout>
  )
}
