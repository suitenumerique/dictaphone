type AudioInputListener = (devices: MediaDeviceInfo[]) => void

// Exclude common monitor/display audio names
const EXCLUDED_INPUTS = [
  'monitor',
  'display',
  'hdmi',
  'dp audio',
  'displayport',
  'nvidia output',
  'amd high definition',
  'intel display audio',
]

/**
 * Manages audio input devices, including device selection, subscribing to device change events,
 * and acquiring media streams from audio input devices.
 */
export class AudioInputManager {
  private listeners = new Set<AudioInputListener>()
  private selectedDeviceId = ''
  private disposed = false

  constructor() {
    if (navigator.mediaDevices?.addEventListener) {
      navigator.mediaDevices.addEventListener(
        'devicechange',
        this.handleDeviceChange
      )
    }
  }

  /**
   * Handles device change events by notifying listeners of updated device list.
   */
  private handleDeviceChange = () => {
    void this.notifyListeners()
  }

  /**
   * Notifies all registered listeners about the updated list of audio input devices.
   * @private
   */
  private async notifyListeners() {
    const devices = await this.listInputDevices()
    for (const listener of this.listeners) {
      listener(devices)
    }
  }

  /**
   * Retrieves the list of available audio input devices.
   * @returns A promise that resolves to an array of MediaDeviceInfo objects representing audio input devices.
   */
  public async listInputDevices() {
    if (!navigator.mediaDevices?.enumerateDevices) {
      return []
    }
    const devices = await navigator.mediaDevices.enumerateDevices()
    return devices.filter(
      (device) =>
        device.kind === 'audioinput' &&
        !EXCLUDED_INPUTS.some((excluded) =>
          (device.label || '').toLowerCase().includes(excluded)
        )
    )
  }

  /**
   * Retrieves the currently selected audio input device ID.
   * If no device is selected, it automatically selects the first available device.
   * @returns A promise that resolves to the selected device ID.
   */
  public async getSelectedDeviceId() {
    if (this.selectedDeviceId) return this.selectedDeviceId

    const inputs = await this.listInputDevices()
    const firstId =
      inputs.find((d) => d.deviceId && d.deviceId !== 'default')?.deviceId ?? ''
    if (firstId) this.selectedDeviceId = firstId // only cache if resolved
    return firstId
  }

  /**
   * Requests permission to access the microphone and updates device labels.
   * @returns A promise that resolves to true if permission is granted, false otherwise.
   */
  public async requestPermission(): Promise<boolean> {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      stream.getTracks().forEach((t) => t.stop()) // release immediately
      await this.notifyListeners() // re-enumerate with labels now visible
      return true
    } catch {
      return false
    }
  }

  /**
   * Retrieves the current permission state for accessing the microphone.
   * @returns A promise that resolves to the current permission state ('granted', 'denied', 'prompt', or 'unsupported').
   */
  public async getPermissionState(): Promise<PermissionState | 'unsupported'> {
    try {
      const result = await navigator.permissions.query({
        name: 'microphone' as PermissionName,
      })
      return result.state
    } catch {
      return 'unsupported'
    }
  }

  /**
   * Selects a specific audio input device by its ID.
   * @param deviceId - The ID of the device to select.
   */
  public async selectDevice(deviceId: string) {
    this.selectedDeviceId = deviceId
    await this.notifyListeners()
  }

  /**
   * Acquires an audio input stream from the selected device or the first available device if none is selected.
   * @param deviceId - Optional ID of the device to acquire the stream from. If not provided, the selected device is used.
   * @returns A promise that resolves to a MediaStream object representing the acquired audio input stream.
   * @throws Error if unable to acquire audio input stream and no device is selected.
   */
  public async acquireStream(deviceId?: string) {
    const selectedId = deviceId ?? (await this.getSelectedDeviceId())
    try {
      return await navigator.mediaDevices.getUserMedia({
        audio: selectedId ? { deviceId: { exact: selectedId } } : true,
      })
    } catch {
      if (!selectedId) {
        throw new Error('Unable to acquire audio input stream')
      }
      return navigator.mediaDevices.getUserMedia({ audio: true })
    }
  }

  /**
   * Subscribes a listener to receive audio input events.
   * @param listener - The listener function to be called when audio input events occur.
   * @returns A function to unsubscribe the listener.
   */
  public subscribe(listener: AudioInputListener) {
    this.listeners.add(listener)
    void this.notifyListeners()
    return () => {
      this.listeners.delete(listener)
    }
  }

  /**
   * Unsubscribes all listeners and releases any acquired audio input stream.
   */
  public dispose() {
    if (this.disposed) {
      return
    }
    this.disposed = true
    this.listeners.clear()
    if (navigator.mediaDevices?.removeEventListener) {
      navigator.mediaDevices.removeEventListener(
        'devicechange',
        this.handleDeviceChange
      )
    }
  }
}
