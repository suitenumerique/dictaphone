// src/services/authService.ts
import { Linking, Platform } from 'react-native'
import { InAppBrowser } from 'react-native-inappbrowser-reborn'
import * as Keychain from 'react-native-keychain'
import { API_URL } from '../api/constants'
import { colors } from '@/components/colors'
import QuickCrypto from 'react-native-quick-crypto'

const REDIRECT_URL = 'assistant-transcripts://auth/callback'
const ACCESS_TOKEN_KEY = 'access_token'
const REFRESH_TOKEN_KEY = 'refresh_token'
const PKCE_VERIFIER_KEY = 'pkce_code_verifier'
const PKCE_STATE_KEY = 'pkce_state'
const OAUTH_TOKEN_URL = `${API_URL}/oauth/token/`
const OAUTH_REFRESH_TOKEN_URL = `${API_URL}/oauth/token/refresh/`

type TokenResponse = {
  refresh: string
  access: string
}

type TokenRequest = {
  code: string
  code_verifier: string
}

// The same route your webapp uses
function buildAuthUrl(
  silent: boolean,
  codeChallenge: string,
  state: string
): string {
  const query = new URLSearchParams({
    silent: String(silent),
    returnTo: '/mobile-login',
    response_type: 'code',
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
    state,
  })

  return `${API_URL}/authenticate/?${query.toString()}`
}

async function storeSecret(service: string, secret: string): Promise<void> {
  await Keychain.setGenericPassword(service, secret, {
    service,
    accessible: Keychain.ACCESSIBLE.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  })
}

async function getSecret(service: string): Promise<string | null> {
  const credentials = await Keychain.getGenericPassword({ service })
  if (!credentials) {
    return null
  }
  return credentials.password
}

async function clearSecret(service: string): Promise<void> {
  await Keychain.resetGenericPassword({ service })
}

async function requestToken(data: TokenRequest): Promise<TokenResponse> {
  const response = await fetch(OAUTH_TOKEN_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  })

  if (!response.ok) {
    throw new Error(`Token request failed with status ${response.status}`)
  }

  const payload = (await response.json()) as Partial<TokenResponse>
  if (!payload.access || !payload.refresh) {
    throw new Error('Token response is missing access_token or refresh_token')
  }

  return {
    access: payload.access,
    refresh: payload.refresh,
  }
}

export async function storeTokens(tokens: TokenResponse): Promise<void> {
  await Promise.all([
    storeSecret(ACCESS_TOKEN_KEY, tokens.access),
    storeSecret(REFRESH_TOKEN_KEY, tokens.refresh),
  ])
}

export async function getAccessToken(): Promise<string | null> {
  return getSecret(ACCESS_TOKEN_KEY)
}

export async function getRefreshToken(): Promise<string | null> {
  return getSecret(REFRESH_TOKEN_KEY)
}

export async function clearAuthState(): Promise<void> {
  await Promise.all([
    clearSecret(ACCESS_TOKEN_KEY),
    clearSecret(REFRESH_TOKEN_KEY),
    clearSecret(PKCE_VERIFIER_KEY),
    clearSecret(PKCE_STATE_KEY),
  ])
}

export async function exchangeCodeForTokens(
  code: string,
  state?: string
): Promise<void> {
  const [codeVerifier, expectedState] = await Promise.all([
    getSecret(PKCE_VERIFIER_KEY),
    getSecret(PKCE_STATE_KEY),
  ])

  if (!codeVerifier) {
    throw new Error('Missing code_verifier for PKCE exchange')
  }

  if (expectedState && state && expectedState !== state) {
    throw new Error('PKCE state mismatch')
  }

  const tokens = await requestToken({
    code,
    code_verifier: codeVerifier,
  })
  await Promise.all([
    storeTokens(tokens),
    clearSecret(PKCE_VERIFIER_KEY),
    clearSecret(PKCE_STATE_KEY),
  ])
}

let refreshPromise: Promise<string | null> | null = null
export async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) {
    return refreshPromise
  }

  refreshPromise = (async () => {
    const refreshToken = await getRefreshToken()
    if (!refreshToken) {
      return null
    }

    try {
      const response = await fetch(OAUTH_REFRESH_TOKEN_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ refresh: refreshToken }),
      })

      if (!response.ok) {
        throw new Error(
          `Refresh token request failed with status ${response.status}`
        )
      }
      const tokensResponse = (await response.json()) as TokenResponse
      if (!tokensResponse.refresh || !tokensResponse.access) {
        throw new Error(
          'Refresh token response missing access token or refresh token'
        )
      }
      await storeTokens(tokensResponse)
      return tokensResponse.access
    } catch {
      await clearAuthState()
      return null
    }
  })()

  try {
    return await refreshPromise
  } finally {
    refreshPromise = null
  }
}

// --- Login: open the backend auth URL in a browser ---
export async function login(): Promise<void> {
  // For reference: https://datatracker.ietf.org/doc/html/rfc7636#section-4.1
  // and https://auth0.com/blog/demystifying-oauth-security-state-vs-nonce-vs-pkce/
  // State is added to prevent CSRF attacks
  const codeVerifier = QuickCrypto.randomBytes(32).toString('base64url')
  const state = QuickCrypto.randomBytes(32).toString('base64url')
  const codeChallenge = QuickCrypto.createHash('sha256')
    .update(codeVerifier)
    .digest('base64url')

  await Promise.all([
    storeSecret(PKCE_VERIFIER_KEY, codeVerifier),
    storeSecret(PKCE_STATE_KEY, state),
  ])

  const url = buildAuthUrl(false, codeChallenge, state)
  const isAvailable = await InAppBrowser.isAvailable()
  if (isAvailable) {
    const res = await InAppBrowser.openAuth(url, REDIRECT_URL, {
      // iOS Properties
      dismissButtonStyle: 'cancel',
      preferredBarTintColor: colors.secondary,
      preferredControlTintColor: 'white',
      readerMode: false,
      animated: true,
      modalPresentationStyle: 'fullScreen',
      modalTransitionStyle: 'coverVertical',
      modalEnabled: true,
      enableBarCollapsing: false,
      // Android Properties
      showTitle: false,
      toolbarColor: colors.secondary,
      secondaryToolbarColor: 'black',
      navigationBarColor: 'black',
      navigationBarDividerColor: 'white',
      enableUrlBarHiding: true,
      enableDefaultShare: false,
      forceCloseOnRedirection: true,
      // Specify full animation resource identifier(package:anim/name)
      // or only resource name(in case of animation bundled with app).
      animations: {
        startEnter: 'slide_in_right',
        startExit: 'slide_out_left',
        endEnter: 'slide_in_left',
        endExit: 'slide_out_right',
      },
      headers: {},
    })
    if (res.type === 'success') {
      // For some reasons on iOS the redirect is not working
      if (Platform.OS === 'ios') {
        Linking.openURL(res.url)
      }
    }
  } else {
    Linking.openURL(url)
  }
}
