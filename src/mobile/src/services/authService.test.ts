import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  values: new Map<string, string>(),
  fetch: vi.fn(),
  resetQueries: vi.fn(),
}))
vi.mock('react-native', () => ({
  Linking: { openURL: vi.fn() },
  Platform: { OS: 'android' },
}))
vi.mock('react-native-inappbrowser-reborn', () => ({
  InAppBrowser: { isAvailable: async () => false },
}))
vi.mock('react-native-keychain', () => ({
  ACCESSIBLE: { WHEN_UNLOCKED_THIS_DEVICE_ONLY: 'device-only' },
  setGenericPassword: async (
    _user: string,
    secret: string,
    { service }: { service: string }
  ) => {
    mocks.values.set(service, secret)
  },
  getGenericPassword: async ({ service }: { service: string }) => {
    const password = mocks.values.get(service)
    return password ? { password } : false
  },
  resetGenericPassword: async ({ service }: { service: string }) => {
    mocks.values.delete(service)
  },
}))
vi.mock('../api/constants', () => ({ API_URL: 'https://api.example/api/v1.0' }))
vi.mock('@/components/colors', () => ({ colors: {} }))
vi.mock('react-native-quick-crypto', () => ({ default: {} }))
vi.mock('@/api/queryClient', () => ({
  queryClient: { resetQueries: mocks.resetQueries },
}))

const original = { access: 'access', refresh: 'refresh', revoke: 'revoke-only' }
const replacement = {
  access: 'access-2',
  refresh: 'refresh-2',
  revoke: 'revoke-only-2',
}
const response = (body: unknown, status = 200) => ({
  ok: status < 400,
  status,
  json: async () => body,
})

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

beforeEach(() => {
  vi.resetModules()
  vi.clearAllMocks()
  mocks.values.clear()
  vi.stubGlobal('fetch', mocks.fetch)
})

describe('session logout', () => {
  it('clears credentials and sends only the logout-only credential', async () => {
    const auth = await import('./authService')
    await auth.storeTokens(original)
    mocks.fetch.mockResolvedValue(
      response({ logout_url: 'https://api.example/logout-ticket' })
    )
    const result = await auth.logoutAuthState()
    expect(result).toEqual({
      revoked: true,
      logoutUrl: 'https://api.example/logout-ticket',
    })
    expect(JSON.parse(mocks.fetch.mock.calls[0][1].body)).toEqual({
      revoke: original.revoke,
    })
    expect(await auth.getAccessToken()).toBeNull()
    expect(await auth.getRefreshToken()).toBeNull()
    expect(mocks.values.has('revoke_token')).toBe(false)
    expect(await auth.refreshAccessToken()).toBeNull()
  })

  it('retains only a pending revocation credential offline and retries after restart', async () => {
    const auth = await import('./authService')
    await auth.storeTokens(original)
    mocks.fetch.mockRejectedValue(new Error('offline'))
    expect((await auth.logoutAuthState()).revoked).toBe(false)
    expect([...mocks.values.keys()]).toEqual(['pending_revocations'])
    expect(JSON.parse(mocks.values.get('pending_revocations')!)).toEqual([
      original.revoke,
    ])
    vi.resetModules()
    mocks.fetch.mockResolvedValue(response({ logout_url: null }))
    const restarted = await import('./authService')
    expect((await restarted.retryPendingRevocations()).revoked).toBe(true)
    expect(JSON.parse(mocks.values.get('pending_revocations')!)).toEqual([])
  })

  it('does not restore credentials when refresh completes during logout', async () => {
    const auth = await import('./authService')
    await auth.storeTokens(original)
    const refreshing = deferred<ReturnType<typeof response>>()
    const started = deferred<void>()
    mocks.fetch.mockImplementation(async (url: string) => {
      if (url.includes('/refresh/')) {
        started.resolve()
        return refreshing.promise
      }
      return response({ logout_url: null })
    })
    const refresh = auth.refreshAccessToken()
    await started.promise
    const logout = auth.logoutAuthState()
    refreshing.resolve(response(replacement))
    expect(await refresh).toBeNull()
    expect((await logout).revoked).toBe(true)
    expect(await auth.getAccessToken()).toBeNull()
    const logoutCall = mocks.fetch.mock.calls.find((call) =>
      call[0].includes('/revoke/')
    )
    expect(JSON.parse(logoutCall![1].body)).toEqual({ revoke: original.revoke })
  })

  it('cancels a late login exchange and revokes the newly issued session', async () => {
    const auth = await import('./authService')
    mocks.values.set('pkce_code_verifier', 'verifier')
    mocks.values.set('pkce_state', 'state')
    const exchanging = deferred<ReturnType<typeof response>>()
    const started = deferred<void>()
    mocks.fetch.mockImplementation(async (url: string) => {
      if (url.endsWith('/oauth/token/')) {
        started.resolve()
        return exchanging.promise
      }
      return response({ logout_url: null })
    })
    const exchange = auth.exchangeCodeForTokens('code', 'state')
    const rejected = expect(exchange).rejects.toThrow('cancelled')
    await started.promise
    const logout = auth.logoutAuthState()
    exchanging.resolve(response(original))
    await rejected
    expect((await logout).revoked).toBe(true)
    expect(await auth.getAccessToken()).toBeNull()
    expect(
      mocks.fetch.mock.calls.some(
        (call) => JSON.parse(call[1].body).revoke === original.revoke
      )
    ).toBe(true)
  })

  it('serializes concurrent refresh calls and stores the rotated credentials', async () => {
    const auth = await import('./authService')
    await auth.storeTokens(original)
    mocks.fetch.mockResolvedValue(response(replacement))
    const tokens = await Promise.all([
      auth.refreshAccessToken(),
      auth.refreshAccessToken(),
    ])
    expect(tokens).toEqual([replacement.access, replacement.access])
    expect(mocks.fetch).toHaveBeenCalledTimes(1)
    expect(await auth.getRefreshToken()).toBe(replacement.refresh)
    expect(mocks.values.get('revoke_token')).toBe(replacement.revoke)
  })

  it('queues revocation when a refresh response is lost and local credentials are cleared', async () => {
    const auth = await import('./authService')
    await auth.storeTokens(original)
    mocks.fetch.mockRejectedValue(new Error('response lost'))
    expect(await auth.refreshAccessToken()).toBeNull()
    await auth.retryPendingRevocations()
    expect(await auth.getAccessToken()).toBeNull()
    expect(JSON.parse(mocks.values.get('pending_revocations')!)).toEqual([
      original.revoke,
    ])
  })

  it('drops expired pending logout credentials without retrying forever', async () => {
    const auth = await import('./authService')
    await auth.storeTokens(original)
    mocks.fetch.mockResolvedValue(response({}, 401))
    expect((await auth.logoutAuthState()).revoked).toBe(true)
    expect(JSON.parse(mocks.values.get('pending_revocations')!)).toEqual([])
  })
})
