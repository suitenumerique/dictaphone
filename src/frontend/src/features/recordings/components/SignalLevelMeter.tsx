import { useEffect, useRef } from 'react'
import type { CSSProperties } from 'react'

const LEVEL_MULTIPLIER = 5
const UPDATE_INTERVAL_MS = 100

export function SignalLevelMeter({
  analyserNode,
  isActive,
  ariaLabel,
}: {
  analyserNode: AnalyserNode | null
  isActive: boolean
  ariaLabel: string
}) {
  const meterRef = useRef<HTMLDivElement | null>(null)
  const lastRenderedPercentRef = useRef(-1)

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
      setMeterPercent(0)
      return
    }

    const samples = new Uint8Array(analyserNode.fftSize)

    const computeLevel = () => {
      if (document.visibilityState !== 'visible') {
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
      setMeterPercent(Math.round(level * 100))
    }

    computeLevel()
    const intervalId = window.setInterval(computeLevel, UPDATE_INTERVAL_MS)

    return () => {
      window.clearInterval(intervalId)
      setMeterPercent(0)
    }
  }, [analyserNode, isActive])

  const meterStyle = {
    '--meter-level': '0%',
  } as CSSProperties

  return (
    <div
      ref={meterRef}
      className={`signal-level-meter ${
        isActive ? 'signal-level-meter--active' : 'signal-level-meter--inactive'
      }`}
      style={meterStyle}
      role="progressbar"
      aria-label={ariaLabel}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={0}
    ></div>
  )
}
