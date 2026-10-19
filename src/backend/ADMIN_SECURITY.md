# Admin account lockout

The Django admin password login locks an account or IP after five failed attempts.
The default cool-off period is 15 minutes. Lockouts are stored in the database.
Account failures count across IP addresses, and IP failures count across accounts
to prevent password spraying. Reaching either threshold blocks admin login.
OIDC and PKCE authentication do not record or reset these attempts.
A successful admin login clears earlier failures. Attempts during lockout do not
extend its duration.

Configure these environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `RATE_LIMIT_ADMIN_LOGIN_FAILURE_LIMIT` | `5` | Failed attempts before lockout |
| `RATE_LIMIT_ADMIN_LOGIN_COOLOFF_HOURS` | `0.25` | Cool-off duration in hours |

After installing dependencies, run `python manage.py migrate` to create the
django-axes tables. Administrators can inspect and reset access attempts in the
admin, or reset attempts for a specific account or IP from the command line:

```sh
python manage.py axes_reset_username admin@example.com
python manage.py axes_reset_ip 192.0.2.1
```

Both account and IP thresholds must be below the limit to allow login. When
resetting a password-spraying lockout, resetting only one account may leave the
IP locked by attempts against other accounts.
