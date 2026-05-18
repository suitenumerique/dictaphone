import type { CSSProperties } from 'react'

export function SignalLevelMeter({
  level,
  isActive,
  ariaLabel,
}: {
  level: number
  isActive: boolean
  ariaLabel: string
}) {
  const meterStyle = {
    '--meter-level': `${Math.round(level * 100)}%`,
  } as CSSProperties

  return (
    <div
      className={`signal-level-meter ${
        isActive ? 'signal-level-meter--active' : 'signal-level-meter--inactive'
      }`}
      style={meterStyle}
      role="progressbar"
      aria-label={ariaLabel}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(level * 100)}
    ></div>
  )
}
