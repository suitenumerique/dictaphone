import { HomeRoute } from '@/features/home'
import { JSX } from 'react'

export const routes: Record<
  'home',
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
    Component: HomeRoute,
  },
}

export type RouteName = keyof typeof routes
