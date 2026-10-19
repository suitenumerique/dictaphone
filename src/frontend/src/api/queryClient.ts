import { isRateLimitError } from './rateLimits'
import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) =>
        !isRateLimitError(error) && failureCount < 3,
    },
  },
})
