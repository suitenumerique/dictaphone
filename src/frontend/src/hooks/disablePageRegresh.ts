import { useEffect } from 'react'

export function useDisablePageRefresh(active: boolean) {
  useEffect(() => {
    if (!active) return

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }

    window.addEventListener('beforeunload', handleBeforeUnload)

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload)
    }
  }, [active])
}
