export function Skeleton({ opacity }: { opacity: number }) {
  return <div className="skeleton" style={{ opacity: `${opacity}%` }} />
}
