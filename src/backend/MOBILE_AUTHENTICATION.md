# Mobile login and logout

Each successful mobile OIDC callback creates a `MobileAuthSession`. The one-use
PKCE code references that session, so provider logout can also invalidate a login
whose code has not yet been exchanged. Every application access and refresh JWT
contains `mobile_session_id`. API authentication and refresh require a matching,
unexpired, unrevoked session. The database is authoritative; do not add an active
session cache without defining its revocation delay.

The session has an absolute lifetime equal to `JWT_REFRESH_TOKEN_LIFETIME_SECONDS`
(default seven days). Rotation never extends that deadline. Access JWTs also
expire no later than the session. Concurrent refresh and logout lock the same
row. Reusing a consumed, validly signed refresh JWT revokes the whole session.
A lost refresh response can therefore require signing in again; clients must
serialize refresh and must not retry the old refresh token automatically.

Token responses contain `access`, `refresh`, and `revoke`. `revoke` is a signed,
session-bound logout-only credential, expiring with the session. It cannot grant
API access or refresh tokens. `POST oauth/token/revoke/` accepts either
`{"revoke": "..."}` or, for existing mobile versions, `{"refresh": "..."}`.
Consumed refresh tokens can still revoke their own session. Revocation is
idempotent and returns `{"logout_url": "..."}` (or null). No access JWT or browser
cookie is required. Revocation deletes the associated Django browser session.
Already authenticated/in-flight requests are not undone.

The mobile app clears application credentials on logout and keeps pending
logout-only credentials in device-only Keychain storage. It retries them on
startup, foregrounding and network reconnection, and shows a pending logout
message when server revocation cannot be confirmed. No implementation can revoke
server credentials immediately while the device is offline. Background retries
revoke the application session; they do not open provider browser windows.

## OIDC

ID tokens needed for logout are encrypted in the database using Fernet with a
purpose-specific key derived from Django `SECRET_KEY`. `SECRET_KEY_FALLBACKS`
supports decrypting tokens during key rotation. No upstream refresh token is
needed. Provider issuer, subject and `sid` come from the verified ID token, not
from unverified token-endpoint fields.

Application logout commits before returning a single-use browser URL. Opening
that URL initiates RP-initiated logout with `id_token_hint` and random state.
The server validates and consumes the callback state before redirecting to the
configured mobile deep link. Tickets and callback states last five minutes and
use the shared Django cache. Browser cancellation or provider failure never
restores application credentials.

Register this additional post-logout redirect with the provider:
`https://<backend>/api/v1.0/oauth/logout/callback/`.
Set `OIDC_OP_LOGOUT_ENDPOINT`, `OIDC_OP_URL` (the exact issuer), and keep
`OIDC_STORE_ID_TOKEN=True`. Configure the provider's back-channel logout URL as
`https://<backend>/api/v1.0/backchannel-logout/` to revoke mobile sessions when SSO
ends elsewhere. Signed logout tokens are validated against provider keys,
issuer, audience, timestamps, events, nonce absence and replay identifiers.
Issuer plus `sid` targets a provider session; issuer plus subject without `sid`
targets all that subject's mobile sessions. Provider logout may affect other
applications sharing the SSO session.

Browser logout through `/logout/` also revokes mobile sessions tied to that Django
browser session and terminates local authentication before leaving for the
provider. Back-channel handling deletes browser sessions linked to mobile logins
with cache-backed Django sessions. Browser-only cached sessions are not indexed
by this mobile model; their back-channel logout remains a separate limitation of
`django-lasuite`. Its browser-only database-backed session handling is retained.

## Deployment and operations

1. Apply migrations, including `0024_mobile_auth_session`, before routing traffic
   to the new backend. Restart all backend workers together: mixed old/new
   authentication workers would retain the old acceptance behavior.
2. Existing mobile JWTs lack a session identifier and are deliberately rejected.
   Users must sign in again. Deploy the backend before the updated mobile app;
   older clients can still use refresh-body logout but lack offline retry and
   cannot follow the new provider logout URL returned by that endpoint. Set the
   supported minimum mobile version if the complete logout behavior is required.
3. Register the provider callback/back-channel URLs above, and verify real logout
   on both iOS and Android with the deployed provider/browser setup.
4. The default Helm chart schedules `manage.py purge_mobile_sessions` and
   `manage.py flushexpiredtokens` daily. Schedule both commands when deploying
   without the chart or overriding its cron jobs. Revoked sessions remain until absolute
   expiry for audit/reuse protection; cleanup removes encrypted ID tokens too.
5. Use the Mobile auth sessions admin actions to revoke selected logins or all
   mobile sessions for the selected users. Credentials are excluded from admin.

Authentication applies to DRF file/media authorization too. Any ingress
`auth_request` caching must not cache successful authorization if immediate
revocation is required. Previously issued direct S3 upload capabilities retain
their own expiry; logout does not recall already downloaded files or uploads
already authorized by object storage.
