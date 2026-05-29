import { useCallback, useEffect, useRef, useState } from 'react'
import { Tooltip } from '@gouvfr-lasuite/cunningham-react'
import { Warning } from '@gouvfr-lasuite/ui-kit'

const UPDATE_INTERVAL_MS = 33
const BAR_SPAWN_INTERVAL_MS = 100
const NO_SOUND_DELAY_MS = 3_000
const BAR_WIDTH_PX = 5
const BAR_GAP_PX = 5
const BAR_STEP_PX = BAR_WIDTH_PX + BAR_GAP_PX
const MIN_BAR_HEIGHT_PX = 4
const MAX_BAR_HEIGHT_PX = 60
const ACTIVE_BAR_COLOR = '#E32C39'
const INACTIVE_BAR_COLOR = '#CFD5DE'
// Lower bound of the speech frequency band (Hz)
// filters out low-frequency rumble and sub-bass noise
const SPEECH_MIN_HZ = 120
// Upper bound of the speech frequency band (Hz)
// covers consonants and sibilance while rejecting high-frequency hiss
const SPEECH_MAX_HZ = 4_000
// Fixed offset subtracted from the gated signal after noise floor removal
// adds hysteresis so near-silence reads as zero
const NOISE_GATE_OFFSET = 0.02
// Exponential smoothing factor for the adaptive noise floor
// lower = slower adaptation, higher = faster tracking
const NOISE_FLOOR_SMOOTHING = 0.08

export function SignalLevelMeter({
  analyserNode,
  isActive,
  ariaLabel,
  noSoundDetectedLabel,
  lowSoundLabel,
  soundOkLabel,
}: {
  analyserNode: AnalyserNode | null
  isActive: boolean
  ariaLabel: string
  noSoundDetectedLabel: string
  lowSoundLabel: string
  soundOkLabel: string
}) {
  const meterRef = useRef<HTMLDivElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const lastRenderedPercentRef = useRef(-1)
  const currentLevelRef = useRef(0)
  const isActiveRef = useRef(isActive)
  const barsRef = useRef<number[]>([])
  const barScrollOffsetRef = useRef(0)
  const noiseFloorRef = useRef(0)
  const zeroSinceRef = useRef<number | null>(null)
  const lowSinceRef = useRef<number | null>(null)
  const [soundStatus, setSoundStatus] = useState<'no-sound' | null>(null)

  const drawBars = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) {
      return
    }

    const ctx = canvas.getContext('2d')
    if (!ctx) {
      return
    }

    const width = canvas.clientWidth
    const height = canvas.clientHeight
    if (width <= 0 || height <= 0) {
      return
    }

    ctx.clearRect(0, 0, width, height)

    const maxVisibleBars = Math.max(1, Math.floor(width / BAR_STEP_PX))
    if (barsRef.current.length > maxVisibleBars) {
      barsRef.current = barsRef.current.slice(-maxVisibleBars)
    }
    const bars = barsRef.current
    const startX =
      width - bars.length * BAR_STEP_PX - barScrollOffsetRef.current

    ctx.fillStyle = isActiveRef.current ? ACTIVE_BAR_COLOR : INACTIVE_BAR_COLOR
    const radius = BAR_WIDTH_PX / 2

    for (let index = 0; index < bars.length; index += 1) {
      const barHeight = Math.min(Math.max(bars[index], 0), height)
      if (barHeight <= 0) {
        continue
      }
      const x = startX + index * BAR_STEP_PX
      const y = (height - barHeight) / 2

      if (typeof ctx.roundRect === 'function') {
        ctx.beginPath()
        ctx.roundRect(x, y, BAR_WIDTH_PX, barHeight, radius)
        ctx.fill()
      } else {
        ctx.fillRect(x, y, BAR_WIDTH_PX, barHeight)
      }
    }

    const fadeWidth = Math.min(42, width * 0.3)
    const leftFade = ctx.createLinearGradient(0, 0, fadeWidth, 0)
    leftFade.addColorStop(0, '#ffffff')
    leftFade.addColorStop(1, 'rgba(255, 255, 255, 0)')
    ctx.fillStyle = leftFade
    ctx.fillRect(0, 0, fadeWidth, height)
  }, [])

  useEffect(() => {
    isActiveRef.current = isActive
    drawBars()
  }, [drawBars, isActive])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) {
      return
    }

    const resizeCanvas = () => {
      const width = Math.max(1, Math.round(canvas.clientWidth))
      const height = Math.max(1, Math.round(canvas.clientHeight))
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width
        canvas.height = height
      }
      drawBars()
    }

    resizeCanvas()
    const resizeObserver = new ResizeObserver(resizeCanvas)
    resizeObserver.observe(canvas)

    return () => {
      resizeObserver.disconnect()
    }
  }, [drawBars])

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
      currentLevelRef.current = percent
      meterElement.setAttribute('aria-valuenow', String(percent))
    }

    if (!isActive || !analyserNode) {
      zeroSinceRef.current = null
      lowSinceRef.current = null
      noiseFloorRef.current = 0
      setSoundStatus(null)
      setMeterPercent(0)
      return
    }

    const frequencySamples = new Uint8Array(analyserNode.frequencyBinCount)
    const frequencyBinSize =
      analyserNode.context.sampleRate / analyserNode.fftSize
    const speechStartBin = Math.max(
      0,
      Math.floor(SPEECH_MIN_HZ / frequencyBinSize)
    )
    const speechEndBin = Math.min(
      frequencySamples.length - 1,
      Math.ceil(SPEECH_MAX_HZ / frequencyBinSize)
    )
    const setStatusFromLevel = (levelPercent: number) => {
      const now = Date.now()

      if (levelPercent === 0) {
        zeroSinceRef.current ??= now
      } else {
        zeroSinceRef.current = null
      }

      if (
        zeroSinceRef.current !== null &&
        now - zeroSinceRef.current >= NO_SOUND_DELAY_MS
      ) {
        setSoundStatus('no-sound')
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

      analyserNode.getByteFrequencyData(frequencySamples)

      let bandEnergySum = 0
      for (let index = speechStartBin; index <= speechEndBin; index += 1) {
        bandEnergySum += frequencySamples[index] / 255
      }
      const speechBinCount = speechEndBin - speechStartBin + 1
      const speechBandEnergy =
        speechBinCount > 0 ? bandEnergySum / speechBinCount : 0

      const gatedLevel = Math.max(
        0,
        speechBandEnergy - noiseFloorRef.current - NOISE_GATE_OFFSET
      )
      const normalizedLevel = Math.min(1, gatedLevel)

      if (normalizedLevel === 0) {
        noiseFloorRef.current =
          noiseFloorRef.current * (1 - NOISE_FLOOR_SMOOTHING) +
          speechBandEnergy * NOISE_FLOOR_SMOOTHING
      }

      const boostedLevel = Math.pow(normalizedLevel, 0.82)
      const levelPercent = Math.round(boostedLevel * 100)

      setMeterPercent(levelPercent)
      setStatusFromLevel(levelPercent)
    }

    computeLevel()
    const intervalId = window.setInterval(computeLevel, UPDATE_INTERVAL_MS)

    return () => {
      window.clearInterval(intervalId)
      zeroSinceRef.current = null
      lowSinceRef.current = null
      noiseFloorRef.current = 0
      setSoundStatus(null)
      setMeterPercent(0)
    }
  }, [analyserNode, isActive])

  useEffect(() => {
    if (!isActive || !analyserNode) {
      return
    }

    const pushBar = () => {
      const normalizedLevel = currentLevelRef.current / 100
      const height =
        MIN_BAR_HEIGHT_PX +
        Math.round((MAX_BAR_HEIGHT_PX - MIN_BAR_HEIGHT_PX) * normalizedLevel)
      const bars = barsRef.current
      bars.push(height)
      const maxVisibleBars = Math.max(
        1,
        Math.floor((canvasRef.current?.clientWidth ?? 0) / BAR_STEP_PX)
      )
      if (bars.length > maxVisibleBars) {
        bars.shift()
      }
    }

    const speedPxPerMs = BAR_STEP_PX / BAR_SPAWN_INTERVAL_MS
    let rafId = 0
    let previousTime = performance.now()

    const animate = (now: number) => {
      const elapsed = now - previousTime
      previousTime = now
      barScrollOffsetRef.current += elapsed * speedPxPerMs

      while (barScrollOffsetRef.current >= BAR_STEP_PX) {
        barScrollOffsetRef.current -= BAR_STEP_PX
        pushBar()
      }

      drawBars()
      rafId = window.requestAnimationFrame(animate)
    }

    rafId = window.requestAnimationFrame(animate)

    return () => {
      window.cancelAnimationFrame(rafId)
      barScrollOffsetRef.current = 0
    }
  }, [analyserNode, drawBars, isActive])

  const statusLabel =
    soundStatus === 'no-sound'
      ? noSoundDetectedLabel
      : soundStatus === 'low-sound'
        ? lowSoundLabel
        : soundOkLabel

  return (
    <div className="signal-level-meter-container">
      {soundStatus === null ? (
        <span role="status" aria-label={statusLabel} className="invisible">
          {/*Just for the proper size */}
          <Warning />
        </span>
      ) : (
        <Tooltip content={statusLabel}>
          <span role="status" aria-label={statusLabel} className={'warning'}>
            <Warning />
          </span>
        </Tooltip>
      )}

      <div
        ref={meterRef}
        className={`signal-level-meter ${
          isActive
            ? 'signal-level-meter--active'
            : 'signal-level-meter--inactive'
        }`}
        role="progressbar"
        aria-label={ariaLabel}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={0}
      >
        <canvas
          ref={canvasRef}
          className="signal-level-meter__canvas"
          aria-hidden="true"
        />
      </div>
    </div>
  )
}
