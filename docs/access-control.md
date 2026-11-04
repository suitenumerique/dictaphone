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
