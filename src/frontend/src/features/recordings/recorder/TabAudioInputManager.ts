const TAB_AUDIO_CONSTRAINTS: MediaStreamConstraints = {
  video: true,
  audio: {
    echoCancellation: false,
    noiseSuppression: false,
    autoGainControl: false,
  },
}

export class TabAudioInputManager {
  private activeStream: MediaStream | null = null

  public isSupported() {
    return !!navigator.mediaDevices?.getDisplayMedia
  }

  public getActiveStream() {
    return this.activeStream
  }

  public async requestStream() {
    if (!this.isSupported()) {
      throw new Error('Tab audio capture is not supported by this browser.')
    }

    this.stopActiveStream()

    const displayStream = await navigator.mediaDevices.getDisplayMedia(
      TAB_AUDIO_CONSTRAINTS
    )
    const audioTracks = displayStream.getAudioTracks()

    // We only keep audio; the mandatory display video track is stopped immediately.
    for (const videoTrack of displayStream.getVideoTracks()) {
      videoTrack.stop()
    }

    if (audioTracks.length === 0) {
      displayStream.getTracks().forEach((track) => track.stop())
      throw new Error('No tab audio source was selected.')
    }

    const stream = new MediaStream(audioTracks)
    this.activeStream = stream
    return stream
  }

  public stopActiveStream() {
    if (!this.activeStream) {
      return
    }

    this.activeStream.getTracks().forEach((track) => {
      track.onended = null
      track.stop()
    })
    this.activeStream = null
  }
}
