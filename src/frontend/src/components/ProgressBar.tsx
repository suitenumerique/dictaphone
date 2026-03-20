import { ProgressBar as ProgressBarAria } from 'react-aria-components'

export function ProgressBar({
  value,
  minValue,
  maxValue,
}: {
  value: number
  minValue: number
  maxValue: number
}) {
  return (
    <ProgressBarAria value={value} minValue={minValue} maxValue={maxValue}>
      {({ percentage, valueText }) => (
        <div className="dictaphone__progress">
          <div className="dictaphone__progress__track">
            <div
              className="dictaphone__progress__fill"
              style={{ width: `${percentage ?? 0}%` }}
            />
          </div>
          <span>{valueText}</span>
        </div>
      )}
    </ProgressBarAria>
  )
}
