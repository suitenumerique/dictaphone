import { HomePage } from '@/pages/HomePage.tsx'
import { JSX } from 'react'
import { RecordingsPage } from '@/pages/RecordingsPage.tsx'

export const routes: Record<
  'home' | 'recordings',
  {
    name: RouteName
    path: RegExp | string
    Component: () => JSX.Element
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    to?: (...args: any[]) => string | URL
  }
> = {
  home: {
    name: 'home',
    path: '/',
    Component: HomePage,
  },
  recordings: {
    name: 'recordings',
    path: '/recordings',
    Component: RecordingsPage,
  },
}

export type RouteName = keyof typeof routes
