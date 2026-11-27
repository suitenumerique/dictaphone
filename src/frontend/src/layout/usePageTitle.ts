import { useEffect } from 'react'

export function usePageTitle(pageTitle: string) {
  useEffect(() => {
    const fullTitle = `${pageTitle} — Transcripts`
    document.title = fullTitle
    const titleElement = document.getElementsByTagName('title')[0]
    if (titleElement) {
      titleElement.textContent = fullTitle
    }
  }, [pageTitle])
}
