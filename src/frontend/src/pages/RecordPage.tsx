import ConnectedLayout from '@/layout/ConnectedLayout.tsx'
import RecordComponent from '@/features/recordings/components/RecordComponent.tsx'

export default function RecordPage() {
  return (
    <ConnectedLayout className="record-parent">
      <RecordComponent />
    </ConnectedLayout>
  )
}
