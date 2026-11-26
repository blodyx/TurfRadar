# TurfRadar - Session update 2026-11-26

## Summary

This session converted TurfRadar's central HTTP user flow from a hard-coded development user into real self-service multi-user authentication suitable for the iPhone PWA.

The main result is verified end-to-end login/logout/re-login on iPhone:

```text
PWA -> Turf e-mail lookup -> Resend magic link -> verification
    -> PWA challenge claim -> session cookie -> authenticated radar
```

## Turf e-mail lookup verified

`POST https://api.turfgame.com/v6/users` was tested using an e-mail lookup.

A valid address associated with Turf user `blodyx` returned the normal Turf profile including Turf ID `28449` and name `blodyx`.

An unknown test address returned `[]`.

A separate lookup by Turf ID confirmed that the v6 response does not expose the user's e-mail address. Registration therefore starts with an e-mail address supplied by the user rather than trying to discover one from a public Turf profile.

## Authentication database migrations

Three migrations were added after migration 008:

### `009_create_user_auth.sql`

Creates:

- `user_auth`
- `auth_tokens`

`user_auth` links a local TurfRadar user to the submitted e-mail address and stores `email_verified_at`.

`auth_tokens` stores only the SHA-256 hash of short-lived one-time verification tokens.

### `010_create_user_sessions.sql`

Creates `user_sessions` with:

- `user_id`
- hashed session token
- expiry
- created timestamp
- last-seen timestamp

Current session lifetime is 30 days.

### `011_create_auth_challenges.sql`

Creates `auth_challenges` with:

- `user_id`
- hashed challenge
- `verified_at`
- `claimed_at`
- expiry

This table bridges the PWA that initiated login and the browser/Safari instance that opens the e-mail magic link.

## Resend integration

Resend is now used to send TurfRadar verification e-mails from a verified subdomain under `farstad.se`.

Secrets/configuration are environment-based. The Resend API key must remain outside Git.

A real delivery test succeeded before the registration flow was connected to Resend.

## Magic-link flow

`POST /api/register` now:

1. accepts `email` and a client-generated `challenge`;
2. validates the e-mail against Turf `/v6/users`;
3. upserts the local Turf user;
4. creates/updates the auth identity;
5. creates a 15-minute verification token;
6. stores only its SHA-256 hash;
7. stores only the hash of the client challenge;
8. sends the raw verification token in a Resend magic link.

`GET /api/auth/verify`:

- rejects invalid, expired or already-used tokens;
- marks the e-mail verified;
- consumes the verification token;
- marks the pending challenge verified.

Single-use behavior was explicitly tested: the same verification token returned HTTP 410 on the second attempt.

## iOS PWA storage issue and challenge/claim solution

A first session implementation set the login cookie directly in the magic-link verification response. This worked in Safari but not reliably in the independently installed iPhone PWA because the PWA can have a separate WebKit storage/cookie context.

The final design avoids assuming Safari and the Home Screen app share cookie storage.

The PWA generates a random challenge using Web Crypto and keeps the raw value locally. After the user clicks the magic link, the PWA polls `POST /api/auth/claim` with that challenge. Once the server sees that the matching challenge is verified, it creates the 30-day session in the PWA request context and sets the cookie there.

This flow was verified in a fresh desktop browser and through logout/login on the iPhone PWA.

## Sessions and protected endpoints

`GET /api/auth/me` verifies that a browser/PWA session identifies the logged-in Turf user without the caller sending Turf ID `28449`.

A shared `get_current_user()` helper is the backend identity boundary. It hashes the cookie token, resolves an unexpired server session and requires a verified e-mail.

The following central endpoints are now session-scoped:

- `/api/radar`
- `/api/settings`
- `/api/push/subscribe`

This removes the old pattern where a user could be selected through `turf_user_id=28449` defaults/query parameters.

`POST /api/auth/logout` deletes the current server session and removes the cookie.

End-to-end logout and re-login were verified successfully on iPhone.

## Frontend refactor

The old monolithic `index.html` was split into:

- `frontend/index.html`
- `frontend/styles.css`
- `frontend/app.js`

The client now includes:

- session check through `/api/auth/me`;
- e-mail login form when unauthenticated;
- Web Crypto challenge creation;
- local pending-challenge state;
- challenge polling every 3 seconds;
- automatic transition to the radar after claim;
- logout;
- session-aware radar/settings/push calls;
- collapsible settings panel;
- browser-local persistence of auto-refresh and settings visibility.

A broken intermediate frontend version duplicated radius controls and failed to cache the logout DOM element. It was replaced with a clean, validated three-file frontend. Login/logout works after the replacement.

## Service worker observation

The current service worker does not cache application assets through the Cache API. It handles:

- immediate activation (`skipWaiting` / `clients.claim`);
- Web Push events;
- notification-click navigation.

Stale frontend behavior briefly observed in Safari was therefore not caused by a TurfRadar-managed Cache API cache. A restart/reload resolved the observed stale UI.

## Current checkpoint

Authentication/onboarding is now considered a working V1 foundation.

Verified:

- Turf e-mail identification;
- Resend delivery;
- one-time verification;
- hashed auth secrets;
- challenge/claim login for isolated PWA storage;
- 30-day sessions;
- current-user endpoint;
- session-scoped radar/settings/push ownership;
- logout;
- iPhone PWA logout and re-login;
- desktop browser onboarding;
- collapsible settings.

## Recommended next steps

1. Add a second real TurfRadar user and verify multi-user isolation end to end.
2. Verify each user's push subscription is associated with the correct local user.
3. Add notification history/cooldown/grouping.
4. Aggregate unikaturfare notifications at owner/player level.
5. Import reliable historical taken-player data when a source is available.
6. Implement off-server PostgreSQL backup and test restore.
