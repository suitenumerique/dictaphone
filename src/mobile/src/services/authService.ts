// src/services/authService.ts
import { authorize, AuthConfiguration } from 'react-native-app-auth';
import * as Keychain from 'react-native-keychain';

const PROCONNECT_CONFIG: AuthConfiguration = {
  issuer: 'https://www.proconnect.gouv.fr',
  clientId: 'YOUR_CLIENT_ID',
  redirectUrl: 'yourapp://auth/callback',
  scopes: ['openid', 'email', 'profile'],
  usePKCE: true,
};

const TOKEN_KEY = 'django_auth_token';

interface DjangoTokens {
  access: string;
  refresh: string;
}

// --- ProConnect login ---
export async function login(): Promise<DjangoTokens> {
  const authResult = await authorize(PROCONNECT_CONFIG);
  const djangoTokens = await exchangeWithBackend(authResult.idToken);
  await storeTokens(djangoTokens);
  return djangoTokens;
}

// --- Send ProConnect id_token to your Django backend ---
async function exchangeWithBackend(idToken: string): Promise<DjangoTokens> {
  const response = await fetch('https://your-api.com/api/auth/mobile-login/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id_token: idToken }),
  });

  if (!response.ok) throw new Error('Backend auth exchange failed');

  return response.json() as Promise<DjangoTokens>;
}

// --- Store Django JWT securely ---
async function storeTokens(tokens: DjangoTokens): Promise<void> {
  await Keychain.setGenericPassword(
    'auth',
    JSON.stringify(tokens),
    { service: TOKEN_KEY }
  );
}

// --- Retrieve stored tokens ---
export async function getTokens(): Promise<DjangoTokens | null> {
  const credentials = await Keychain.getGenericPassword({ service: TOKEN_KEY });
  if (!credentials) return null;
  return JSON.parse(credentials.password) as DjangoTokens;
}

// --- Refresh Django JWT using the refresh token ---
export async function refreshAccessToken(): Promise<string> {
  const tokens = await getTokens();
  if (!tokens?.refresh) throw new Error('No refresh token available');

  const response = await fetch('https://your-api.com/api/auth/token/refresh/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh: tokens.refresh }),
  });

  if (!response.ok) throw new Error('Token refresh failed');

  const { access } = await response.json() as Pick<DjangoTokens, 'access'>;
  await storeTokens({ access, refresh: tokens.refresh });

  return access;
}

// --- Logout ---
export async function logout(): Promise<void> {
  await Keychain.resetGenericPassword({ service: TOKEN_KEY });
}
