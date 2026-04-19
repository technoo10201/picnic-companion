# Security

## Credentials

- **Email + password** are only passed at login time and only to
  `storefront-prod.<cc>.picnicinternational.com/api/15/user/login`.
- The password is **MD5-hashed client-side** (matching the mobile app) before
  being sent. No plaintext password ever leaves the process.
- Once logged in, the integration only holds the **JWT** (`x-picnic-auth`),
  not the password. The password is discarded.

## Where the JWT lives

The JWT is stored in `<HA-config>/.storage/core.config_entries`, on the
config entry's `data.auth_key` field. Access is managed by Home Assistant
(file permissions come from its runtime).

The full HA configuration directory is `.gitignore`d via the root
`.gitignore`:

```
homeassistant/config/
```

## JWT contents

A decoded Picnic JWT payload:

```json
{
  "sub": "<user_id>",
  "pc:clid": 30100,
  "pc:pv:enabled": true,
  "pc:pv:verified": true,
  "pc:2fa": "VERIFIED",
  "pc:role": "STANDARD_USER",
  "pc:loc": "<household-hash>",
  "pc:did": "<device-id>",
  "pc:logints": 1776509806697,
  "iss": "picnic-dev",
  "exp": 1792061875,
  "iat": 1776509875,
  "jti": "<token-id>"
}
```

### Fields worth flagging

- `sub` is your Picnic user id — not secret per se, but links you to
  deliveries and household data.
- `pc:did` is a device identifier Picnic binds to the session at 2FA time.
  Losing it forces a new SMS challenge.
- `pc:loc` is a hashed household id — not reversible.
- Never contains email, phone, or address.

The `api.decode_token_exp()` helper extracts `iat` / `exp` without verifying
the signature (we don't have Picnic's public key). The integration trusts
them purely for timing the 7-day Repair notification.

## Token rotation

Picnic issues a new JWT every so often via the `x-picnic-auth` response
header on API calls. `PicnicSession.request()` captures it and, if a
persistence path is configured, writes it back. This means:

- An actively-used integration (HA polling every 1-60 min) stays signed in
  indefinitely.
- A dormant install will hit expiry at 180 days and raise the
  `token_expired` Repair.

## 2FA

First login from any new device hits `second_factor_authentication_required`.
The mobile app and this integration both call:

1. `POST /user/2fa/generate` `{channel: "SMS"}` — triggers an SMS
2. `POST /user/2fa/verify` `{otp: "<6 digits>"}`

The code is single-use and time-bound. Never logged in the integration.

## Rate limiting

Failing `login` 5+ times in a short window triggers an `AUTH_BLOCKED`
response that persists for ~1 hour — the account is locked on both the
mobile app and any API client. The integration surfaces the underlying
error message; don't loop retries on failed credentials.

## Reporting vulnerabilities

Security issues (e.g. a code path that leaks tokens, or accidental
persistence of secrets to a non-gitignored location) should be reported
privately via the repository's security advisory feature.
