type PaginationProps = {
  page: number
  pageSize: number
  totalItems: number
  onPageChange: (page: number) => void
  ariaLabel: string
  previousAriaLabel: string
  nextAriaLabel: string
}

export function Pagination({
  page,
  pageSize,
  totalItems,
  onPageChange,
  ariaLabel,
  previousAriaLabel,
  nextAriaLabel,
}: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize))

  if (totalPages <= 1) {
    return null
  }

  const previousDisabled = page <= 1
  const nextDisabled = page >= totalPages

  return (
    <nav className="pagination" aria-label={ariaLabel}>
      <button
        type="button"
        className="pagination__button"
        onClick={() => onPageChange(page - 1)}
        disabled={previousDisabled}
        aria-label={previousAriaLabel}
      >
        <span className="material-icons" aria-hidden="true">
          chevron_left
        </span>
      </button>
      <p className="pagination__status" aria-live="polite">
        {page} / {totalPages}
      </p>
      <button
        type="button"
        className="pagination__button"
        onClick={() => onPageChange(page + 1)}
        disabled={nextDisabled}
        aria-label={nextAriaLabel}
      >
        <span className="material-icons" aria-hidden="true">
          chevron_right
        </span>
      </button>
    </nav>
  )
}
