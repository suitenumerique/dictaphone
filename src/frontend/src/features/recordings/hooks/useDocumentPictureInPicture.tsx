import { ReactNode, useCallback, useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'

type DocumentPictureInPictureController = {
  requestWindow: (options?: {
    width?: number
    height?: number
  }) => Promise<Window>
}

const copyStylesToWindow = (source: Document, target: Document) => {
  const stylesheets = source.querySelectorAll('link[rel="stylesheet"], style')
  stylesheets.forEach((node) => {
    target.head.appendChild(node.cloneNode(true))
  })
}

const getDocumentPictureInPicture = () =>
  (
    window as Window & {
      documentPictureInPicture?: DocumentPictureInPictureController
    }
  ).documentPictureInPicture

export const isDocumentPictureInPictureSupported = () =>
  !!getDocumentPictureInPicture()?.requestWindow

export const useDocumentPictureInPicture = ({
  enabled,
  width = 340,
  height = 320,
  children,
}: {
  enabled: boolean
  width?: number
  height?: number
  children: ReactNode
}) => {
  const [pipWindow, setPipWindow] = useState<Window | null>(null)
  const supported = isDocumentPictureInPictureSupported()

  const openWindow = useCallback(async () => {
    if (pipWindow || !supported) {
      return
    }
    try {
      const nextWindow = await getDocumentPictureInPicture()!.requestWindow({
        width,
        height,
      })
      copyStylesToWindow(document, nextWindow.document)
      nextWindow.document.body.classList.add('record-pip-window')
      setPipWindow(nextWindow)
    } catch {
      // Unsupported or blocked by browser/user gesture constraints.
    }
  }, [height, pipWindow, supported, width])

  useEffect(() => {
    if (!enabled) {
      pipWindow?.close()
      return
    }

    if (pipWindow || !supported) {
      return
    }

    const timeoutId = window.setTimeout(() => {
      void openWindow()
    }, 0)
    return () => {
      window.clearTimeout(timeoutId)
    }
  }, [enabled, openWindow, pipWindow, supported])

  useEffect(() => {
    if (!pipWindow) {
      return
    }

    const handleClose = () => {
      setPipWindow(null)
    }
    pipWindow.addEventListener('pagehide', handleClose)
    pipWindow.addEventListener('beforeunload', handleClose)

    return () => {
      pipWindow.removeEventListener('pagehide', handleClose)
      pipWindow.removeEventListener('beforeunload', handleClose)
    }
  }, [pipWindow])

  const portal = useMemo(
    () => (pipWindow ? createPortal(children, pipWindow.document.body) : null),
    [children, pipWindow]
  )

  return {
    portal,
    openWindow,
    isOpen: !!pipWindow,
    supported,
  }
}
