// src/services/authService.ts
import { Linking } from 'react-native';
import { InAppBrowser } from 'react-native-inappbrowser-reborn';
import * as Keychain from 'react-native-keychain';

const BACKEND_URL =
  'https://dictaphone-staging.beta.numerique.gouv.fr/api/v1.0';
const SESSION_COOKIE_NAME = 'sessionid';
const API_REDIRECT_URL = `${BACKEND_URL}/mobile-redirect/`;
const REDIRECT_URL = 'lasuite-dictaphone://auth/callback';

// The same route your webapp uses
function buildAuthUrl(silent: boolean, returnTo: string): string {
  return (
    `${BACKEND_URL}/authenticate/` +
    `?silent=${encodeURIComponent(silent)}` +
    `&returnTo=${encodeURIComponent(returnTo)}`
  );
}

export async function storeSessionCookie(cookie: string): Promise<void> {
  await Keychain.setInternetCredentials(
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    cookie,
  );
}

// --- Login: open the backend auth URL in a browser, capture the session cookie ---
export async function login(): Promise<void> {
  const url = buildAuthUrl(false, API_REDIRECT_URL);
  const isAvailable = await InAppBrowser.isAvailable();
  if (isAvailable) {
    const result = await InAppBrowser.openAuth(url, REDIRECT_URL, {
      // iOS Properties
      dismissButtonStyle: 'cancel',
      preferredBarTintColor: '#453AA4',
      preferredControlTintColor: 'white',
      readerMode: false,
      animated: true,
      modalPresentationStyle: 'fullScreen',
      modalTransitionStyle: 'coverVertical',
      modalEnabled: true,
      enableBarCollapsing: false,
      // Android Properties
      showTitle: false,
      toolbarColor: '#6200EE',
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
      headers: {
      },
    });
    if (result.type === 'success') {
      const sessionId = result.url.split('?sessionid=')[1];
      await storeSessionCookie(sessionId);
    }
  } else {
    Linking.openURL(url);
  }
}

//
// // --- Check if we have a session cookie (i.e. user is logged in) ---
// export async function isAuthenticated(): Promise<boolean> {
//   const cookie = await getSessionCookie();
//   return cookie !== null;
// }

// --- Logout: clear all cookies ---
export async function logout(): Promise<void> {
  await Keychain.resetGenericPassword();
}
