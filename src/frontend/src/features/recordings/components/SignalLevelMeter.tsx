import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'

const LEVEL_MULTIPLIER = 5
const UPDATE_INTERVAL_MS = 100
const NO_SOUND_DELAY_MS = 3_000
const LOW_SOUND_DELAY_MS = 10_000
const LOW_SOUND_THRESHOLD = 5

export function SignalLevelMeter({
  analyserNode,
  isActive,
  ariaLabel,
  noSoundDetectedLabel,
  lowSoundLabel,
}: {
  analyserNode: AnalyserNode | null
  isActive: boolean
  ariaLabel: string
  noSoundDetectedLabel: string
  lowSoundLabel: string
}) {
  const meterRef = useRef<HTMLDivElement | null>(null)
  const lastRenderedPercentRef = useRef(-1)
  const zeroSinceRef = useRef<number | null>(null)
  const lowSinceRef = useRef<number | null>(null)
  const [soundStatus, setSoundStatus] = useState<
    'no-sound' | 'low-sound' | null
  >(null)

  useEffect(() => {
    const meterElement = meterRef.current
    if (!meterElement) {
      return
    }

    const setMeterPercent = (percent: number) => {
      if (percent === lastRenderedPercentRef.current) {
        return
      }
      lastRenderedPercentRef.current = percent
      meterElement.style.setProperty('--meter-level', `${percent}%`)
      meterElement.setAttribute('aria-valuenow', String(percent))
    }

    if (!isActive || !analyserNode) {
      zeroSinceRef.current = null
      lowSinceRef.current = null
      setSoundStatus(null)
      setMeterPercent(0)
      return
    }

    const samples = new Uint8Array(analyserNode.fftSize)
    const setStatusFromLevel = (levelPercent: number) => {
      const now = Date.now()

      if (levelPercent === 0) {
        zeroSinceRef.current ??= now
      } else {
        zeroSinceRef.current = null
      }

      if (levelPercent < LOW_SOUND_THRESHOLD) {
        lowSinceRef.current ??= now
      } else {
        lowSinceRef.current = null
      }

      if (
        zeroSinceRef.current !== null &&
        now - zeroSinceRef.current >= NO_SOUND_DELAY_MS
      ) {
        setSoundStatus('no-sound')
        return
      }

      if (
        lowSinceRef.current !== null &&
        now - lowSinceRef.current >= LOW_SOUND_DELAY_MS
      ) {
        setSoundStatus('low-sound')
        return
      }

      setSoundStatus(null)
    }

    const computeLevel = () => {
      if (document.visibilityState !== 'visible') {
        zeroSinceRef.current = null
        lowSinceRef.current = null
        setSoundStatus(null)
        setMeterPercent(0)
        return
      }

      analyserNode.getByteTimeDomainData(samples)
      let squareSum = 0
      for (const sample of samples) {
        const centered = (sample - 128) / 128
        squareSum += centered * centered
      }
      const rms = Math.sqrt(squareSum / samples.length)
      const level = Math.min(1, rms * LEVEL_MULTIPLIER)
      const levelPercent = Math.round(level * 100)
      setMeterPercent(levelPercent)
      setStatusFromLevel(levelPercent)
    }

    computeLevel()
    const intervalId = window.setInterval(computeLevel, UPDATE_INTERVAL_MS)

    return () => {
      window.clearInterval(intervalId)
      zeroSinceRef.current = null
      lowSinceRef.current = null
      setSoundStatus(null)
      setMeterPercent(0)
    }
  }, [analyserNode, isActive])

  const meterStyle = {
    '--meter-level': '0%',
  } as CSSProperties

  const statusLabel =
    soundStatus === 'no-sound'
      ? noSoundDetectedLabel
      : soundStatus === 'low-sound'
        ? lowSoundLabel
        : null

  return (
    <div className="signal-level-meter-container">
      <div
        ref={meterRef}
        className={`signal-level-meter ${
          isActive
            ? 'signal-level-meter--active'
            : 'signal-level-meter--inactive'
        }`}
        style={meterStyle}
        role="progressbar"
        aria-label={ariaLabel}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={0}
      ></div>
      {statusLabel && (
        <p className="signal-level-meter__status" role="status">
          {statusLabel}
        </p>
      )}
    </div>
  )
}
