import { useEffect, useRef } from 'react'

export function useDisablePageRefresh(active: boolean, alertLabel: string) {
  const initialized = useRef(false)

  useEffect(() => {
    if (!active) return

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }

    if (!initialized.current) {
      history.pushState(null, '', location.href)
      initialized.current = true
    }

    const handlePopState = () => {
      history.pushState(null, '', location.href)
      alert(alertLabel)
    }

    window.addEventListener('popstate', handlePopState)

    window.addEventListener('beforeunload', handleBeforeUnload)

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload)
      window.removeEventListener('popstate', handlePopState)
    }
  }, [active, alertLabel])
}
