import { SignalLevelMeter } from '@/features/recordings/components/SignalLevelMeter.tsx'
import '@/features/recordings/components/RecordingPictureInPicturePanel.scss'
import { Button } from '@gouvfr-lasuite/cunningham-react'

type AudioInputOption = {
  deviceId: string
  label: string
}

export function RecordingPictureInPicturePanel({
  statusLabel,
  durationLabel,
  analyserNode,
  isRecording,
  isPaused,
  onPauseResume,
  onStop,
  audioInputs,
  selectedAudioInputId,
  onSelectAudioInput,
  sourceLabel,
  tabAudioSupported,
  tabAudioLabel,
  tabAudioButtonLabel,
  onTabAudioAction,
  soundLevelAriaLabel,
  noSoundDetectedLabel,
  lowSoundLabel,
  soundOkLabel,
  tabAudioStatusLabel,
}: {
  statusLabel: string
  durationLabel: string
  analyserNode: AnalyserNode | null
  isRecording: boolean
  isPaused: boolean
  onPauseResume: () => void
  onStop: () => void
  audioInputs: AudioInputOption[]
  selectedAudioInputId: string
  onSelectAudioInput: (deviceId: string) => void
  sourceLabel: string
  tabAudioSupported: boolean
  tabAudioLabel: string | null
  tabAudioButtonLabel: string
  onTabAudioAction: () => void
  soundLevelAriaLabel: string
  noSoundDetectedLabel: string
  lowSoundLabel: string
  soundOkLabel: string
  tabAudioStatusLabel: string
}) {
  return (
    <section className="record-pip-panel" aria-label={statusLabel}>

      <div className="record-pip-panel__meter">
        <SignalLevelMeter
          analyserNode={analyserNode}
          isActive={isRecording}
          ariaLabel={soundLevelAriaLabel}
          noSoundDetectedLabel={noSoundDetectedLabel}
          lowSoundLabel={lowSoundLabel}
          soundOkLabel={soundOkLabel}
        />
      </div>

      <span className="record-pip-panel__timer">{durationLabel}</span>

      <label className="record-pip-panel__field" aria-label={sourceLabel}>
        <select
          value={selectedAudioInputId}
          onChange={(event) => onSelectAudioInput(event.target.value)}
          disabled={audioInputs.length === 0}
        >
          {audioInputs.length === 0 && <option value="">-</option>}
          {audioInputs.map((input) => (
            <option key={input.deviceId} value={input.deviceId}>
              {input.label}
            </option>
          ))}
        </select>
      </label>

      {tabAudioSupported && (
        <div className="record-pip-panel__tab-audio">
          <strong title={tabAudioLabel ?? tabAudioStatusLabel}>
            {tabAudioLabel ?? tabAudioStatusLabel}
          </strong>
          <Button size="nano" color="neutral" onClick={onTabAudioAction}>
            {tabAudioButtonLabel}
          </Button>
        </div>
      )}

      <div className="record-pip-panel__actions">
        <Button color="neutral" size="nano" onClick={onPauseResume}>
          {isPaused ? '▶' : 'II'}
        </Button>
        <Button color="error" size="nano" onClick={onStop}>
          ■
        </Button>
      </div>
    </section>
  )
}
