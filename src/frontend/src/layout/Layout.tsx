import { type ReactNode } from 'react'

export type Layout = 'fullpage' | 'centered'

/**
 * Layout component for the app.
 *
 * This component is meant to be used as a wrapper around the whole app.
 * In a specific page, use the `Screen` component and change its props to change global page layout.
 */
export const Layout = ({ children }: { children: ReactNode }) => {
  return (
    <>
      <div>
        <main>{children}</main>
      </div>
    </>
  )
}
