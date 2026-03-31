import { useSummary } from '@/features/ai-jobs/api/fetch.ts'
import { ApiAiJob } from '@/features/ai-jobs/api/types.ts'
import { useTranslation } from 'react-i18next'

export function Summary({
  lastAiJobSummary,
}: {
  lastAiJobSummary: ApiAiJob | null
}) {
  const { t } = useTranslation('recordings')
  const summaryQ = useSummary(lastAiJobSummary)

  return (
    <section className="recording-page__panel">
      <header className="recording-page__panel-header">
        <h2>{t('summary.title')}</h2>
      </header>

      {lastAiJobSummary?.status === 'failed' && (
        <div className="recording-page__state">
          {t('summary.status.failed')}
        </div>
      )}

      {lastAiJobSummary?.status === 'pending' && (
        <div className="recording-page__state">
          {t('summary.status.pending')}
        </div>
      )}

      {summaryQ.data && (
        <div className="recording-page__summary">{summaryQ.data}</div>
      )}
    </section>
  )
}
