# App access control

Set `OIDC_ALLOWED_ROLES=priviledged_user` to restrict processing to users with a
matching role in the OIDC `roles` claim. Use commas for multiple roles; leave empty
to allow everyone. Request the provider's `roles` scope if needed.

Restricted users can still sign in, manage existing files, and read results.
Creating files/upload policies, finalizing uploads, and retrying AI jobs return
HTTP 403. This does not end sessions or invalidate mobile JWTs. Previously issued
storage upload policies work until expiry, but API finalization remains blocked.

## Access status and exceptions

`GET /api/v1.0/users/me/` returns HTTP 200 with two read-only fields:

| `access_status` | Meaning | `is_restricted` |
| --- | --- | --- |
| `allowed` | Matching role, active email bypass, or role policy disabled | `false` |
| `restricted` | Roles received, but none match (including an empty list) | `true` |
| `unknown` | Role policy enabled, but no usable roles claim received | `true` |

Existing users without stored roles have `unknown` status unless bypassed or the
role policy is disabled. Both `restricted` and `unknown` block processing.

Manage exceptions in Django admin under **Access bypass emails**. Matching ignores
case and surrounding whitespace. Active entries with no expiry or a future expiry
grant access; changes and expiration apply on the next API request.

Roles and optional organization SIRET refresh on authentication, so provider role
changes require reauthentication. Clients cannot edit stored roles or access status.

For `unknown`, clients should offer reauthentication and fetch `/users/me/`
afterward. Wait until recording, paused recording, and local saving/finalization
have finished and audio is safely saved before logout, sign-in navigation, or user
switching. Only the client can determine when this is safe. If roles remain
missing, keep `unknown` without forcing repeated logins.

## Local Keycloak development

Docker Compose and `make start-tilt-keycloak` share `docker/auth/realm.json` and use:

```env
OIDC_ALLOWED_ROLES=priviledged_user
OIDC_RP_SCOPES=openid email roles
```

The `dictaphone` client exposes realm roles as a flat `roles` array in UserInfo,
ID tokens, and access tokens. Existing development and browser-test users have
`priviledged_user`.

To test restrictions, sign in with `user-restricted` / `password-restricted`
(only the `user` role). Expect `restricted` status and HTTP 403 for uploads and
retries. Add `restricted@dictaphone.world` to **Access bypass emails** to allow
processing on the next request.

### Existing installations

For Compose, copy the settings above into the ignored `env.d/development/common`
file and recreate the backend and worker containers.

Keycloak imports only new realms. For an existing Compose or Tilt database, use
the Keycloak admin console to:

1. Create realm roles `user` and `priviledged_user`; assign `priviledged_user` to
   existing development users.
2. Add a **User Realm Role** mapper to the `dictaphone` client's dedicated scope:
   claim name `roles`, JSON type `String`, multivalued enabled, included in
   UserInfo, ID tokens, and access tokens.
3. Create the restricted test user above with only `user`, and sign in again
   after role changes.

A fresh Keycloak database needs no manual setup.
