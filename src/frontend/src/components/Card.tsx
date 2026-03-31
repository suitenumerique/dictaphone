import { PropsWithChildren, ReactNode, useId } from 'react'
import clsx from 'clsx'

type CardProps = PropsWithChildren<{
  title: ReactNode
  action?: ReactNode
  contentAriaLabel?: string
  className?: string
}>

export function Card({ title, action, contentAriaLabel, children, className }: CardProps) {
  const titleId = useId()

  return (
    <section className={clsx('card', className)} aria-labelledby={titleId}>
      <header className="card__header">
        <h2 id={titleId} className="card__title">
          {title}
        </h2>
        {action ? <div className="card__action">{action}</div> : null}
      </header>
      <hr className="card__separator" aria-hidden="true" />
      <div className="card__content" aria-label={contentAriaLabel}>
        {children}
      </div>
    </section>
  )
}
