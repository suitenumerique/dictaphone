// Console autocapture may stringify an error before PostHog builds its exception
// list, so check both the exception type and its serialized value.
export const filterException = <
  T extends {
    event: string
    properties?: Record<string, unknown>
  },
>(
  event: T | null
): T | null => {
  if (event?.event !== '$exception') return event
  const exceptions = event.properties?.$exception_list
  if (!Array.isArray(exceptions)) return event
  const ignored = exceptions.some((exception: unknown) => {
    if (!exception || typeof exception !== 'object') return false
    const { type, value } = exception as { type?: unknown; value?: unknown }
    return [type, value].some(
      (text) =>
        typeof text === 'string' &&
        (/\bPostHogFetchNetworkError\b/.test(text) ||
          /\bNetwork error while fetching PostHog\b/.test(text) ||
          /\bApi error 401\b/i.test(text) ||
          /\btoken request failed with status 401\b/i.test(text) ||
          /\bHTTP error while fetching PostHog: status=401\b/.test(text))
    )
  })
  return ignored ? null : event
}
