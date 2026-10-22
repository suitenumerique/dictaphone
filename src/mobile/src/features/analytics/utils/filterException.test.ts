import { describe, expect, it } from 'vitest'
import { filterException } from './filterException'

const exception = (type: string, value: string) => ({
  event: '$exception',
  properties: { $exception_list: [{ type, value }] },
})

describe('PostHog exception filter', () => {
  it.each([
    ['Error', 'Api error 401'],
    ['ApiError', 'Api error 401 (POST /files/abc/upload-ended/)'],
    ['Error', 'Error creating file: [Error: Api error 401]'],
    ['PostHogFetchNetworkError', 'Network request failed'],
    ['Error', 'PostHogFetchNetworkError: Network request failed'],
    ['Error', 'Network error while fetching PostHog'],
    ['Error', 'Refresh token request failed with status 401'],
    [
      'PostHogFetchHttpError',
      'HTTP error while fetching PostHog: status=401, reqByteLength=123',
    ],
  ])('drops expected exception %s: %s', (type, value) => {
    expect(filterException(exception(type, value))).toBeNull()
  })

  it.each([
    ['Error', 'Api error 403'],
    ['Error', 'Api error 500'],
    ['TypeError', 'Network request failed'],
    ['Error', 'Api error 4010'],
    ['Error', 'Failure at line 401'],
  ])('retains other exceptions %s: %s', (type, value) => {
    const event = exception(type, value)
    expect(filterException(event)).toBe(event)
  })

  it('handles nested causes and preserves unrelated analytics events', () => {
    expect(
      filterException({
        event: '$exception',
        properties: {
          $exception_list: [
            { type: 'Error', value: 'Unhandled rejection' },
            { type: 'Error', value: 'Api error 401' },
          ],
        },
      })
    ).toBeNull()
    const event = { event: 'screen', properties: { text: 'Api error 401' } }
    expect(filterException(event)).toBe(event)
    expect(filterException(null)).toBeNull()
    expect(filterException({ event: '$exception' })).toEqual({
      event: '$exception',
    })
  })
})
