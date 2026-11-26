# TurfRadar API Reference

Last updated: 2026-11-26

This document records API behavior used or verified while building TurfRadar.

## Turf API v6 dependencies

Base URL: `https://api.turfgame.com/v6`

Production logic uses Turf API v6.

### `GET /v6/zones/all`

Full Turf zone bootstrap. Use compressed transfer. Stable Turf zone IDs are used as `zones.id`. The endpoint is rate-limited and should not be repeatedly fetched during development.

### `GET /v6/feeds/takeover`

Optional `afterDate` query. TurfRadar uses the latest processed timestamp minus two minutes for deliberate overlap. Zone state is upserted by stable Turf zone ID.

### `GET /v6/rounds`

Used to identify the active round and detect real round transitions.

### `POST /v6/users`

Supported/verified lookup forms include Turf ID and e-mail.

ID example:

```json
[{"id":28449}]
```

E-mail example used by onboarding:

```json
[{"email":"user@example.com"}]
```

A valid e-mail lookup returns the normal Turf user profile including numeric `id` and `name`. An unknown e-mail returned `[]` during verification on 2026-11-26.

Querying by Turf ID did not return an e-mail address during testing.

### `GET /v6/users/location`

Returns currently visible Turf users with ID/name/latitude/longitude. TurfRadar records observation time locally and retains last-known position when a registered user is absent from the current feed.

## TurfRadar HTTP API

Public prefix: `https://farstad.se/turfradar/api`

Protected user endpoints use the `turfradar_session` cookie. The authenticated user must not be selected with a Turf ID query parameter.

### Health

`GET /api/health`

```json
{
  "status": "ok",
  "service": "TurfRadar"
}
```

### Register / start login

`POST /api/register`

Request:

```json
{
  "email": "user@example.com",
  "challenge": "client-generated-random-challenge"
}
```

Behavior:

1. Looks up the e-mail through Turf `/v6/users`.
2. Upserts the local user and auth identity.
3. Hashes and stores the one-time verification token.
4. Hashes and stores the PWA challenge.
5. Sends a 15-minute magic link through Resend.

Example success response:

```json
{
  "status": "verification_sent",
  "turfUserId": 28449,
  "turfName": "blodyx"
}
```

The raw verification token is not returned by the production registration response.

### Verify e-mail

`GET /api/auth/verify?token=...`

Behavior:

- SHA-256 hashes the supplied token and matches `auth_tokens`.
- Rejects missing, used or expired tokens.
- Sets `user_auth.email_verified_at`.
- Marks the verification token used.
- Marks the pending unclaimed login challenge for that user verified.

Success:

```json
{
  "verified": true,
  "turfUserId": 28449,
  "turfName": "blodyx"
}
```

A verification token is single-use. Reuse returns HTTP 410.

### Claim verified login

`POST /api/auth/claim`

Request:

```json
{
  "challenge": "same-client-generated-random-challenge"
}
```

If the magic link has not been verified yet:

```json
{
  "authenticated": false,
  "status": "waiting_for_verification"
}
```

After verification, a valid unclaimed challenge creates a 30-day session and sets cookie `turfradar_session` with `HttpOnly`, `Secure`, `SameSite=Lax`, path `/turfradar`.

Success:

```json
{
  "authenticated": true,
  "turfUserId": 28449,
  "turfName": "blodyx"
}
```

Challenges are single-use and expire after 15 minutes.

### Current user

`GET /api/auth/me`

Requires a valid session cookie.

Example:

```json
{
  "authenticated": true,
  "turfUserId": 28449,
  "turfName": "blodyx",
  "email": "user@example.com"
}
```

### Logout

`POST /api/auth/logout`

Deletes the current server session and removes the session cookie.

```json
{
  "authenticated": false
}
```

### Radar

`GET /api/radar`

Requires authentication. User identity comes from the session.

Response contains:

- authenticated user's Turf ID/name;
- radius and radar-enabled state;
- latest known position and position age;
- count of nearby zones and known owners;
- nearest zones with owner/region/distance metadata.

The dashboard may inspect radar state even when `radarEnabled` is false. The flag controls active radar/notification behavior, not UI visibility or historical/profile collection.

### Settings

`PATCH /api/settings`

Requires authentication. Changes only the authenticated user's row.

Supported request fields:

```json
{
  "radiusM": 2000,
  "radarEnabled": true
}
```

Allowed V1 radii:

- 500 m
- 1000 m
- 2000 m
- 5000 m

Fields can be changed independently. Dashboard auto-refresh and settings-panel visibility are browser-local, not server settings.

### Push public key

`GET /api/push/public-key`

Returns the public VAPID application-server key. This value is public by design.

### Push subscribe

`POST /api/push/subscribe`

Requires authentication. Subscription ownership is taken from the current session, not a Turf ID request parameter.

Request is a browser `PushSubscription` JSON object:

```json
{
  "endpoint": "https://push-service.example/...",
  "keys": {
    "p256dh": "...",
    "auth": "..."
  }
}
```

Subscriptions are upserted by endpoint and associated with the authenticated local user.

### Push test helper

The development-only Python helper can send a manual Web Push from inside the container. It must not be exposed as an unauthenticated public HTTP endpoint.
