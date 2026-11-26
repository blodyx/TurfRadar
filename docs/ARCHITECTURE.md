# TurfRadar Architecture

Last updated: 2026-11-26

## Purpose

TurfRadar is a proximity and notification engine for Turf. It maintains a local model of the Turf world, tracks registered users, performs spatial searches with PostGIS, records observed opponent history and surfaces nearby opportunities through a mobile-first PWA.

V1 optimizes for correctness, simple operation and useful notifications rather than routing or advanced statistics.

## High-level architecture

```text
Turf API v6
  |-- /zones/all
  |-- /feeds/takeover
  |-- /rounds
  |-- /users
  `-- /users/location
          |
          v
PostgreSQL 17 + PostGIS 3.5
          |
          |-- takeover-worker
          |-- round-worker
          |-- location-worker
          |-- radar-worker
          `-- user_sync
          |
          v
FastAPI :8000
  |-- auth/onboarding
  |-- radar/settings
  `-- Web Push subscription
          |
          v
Caddy / HTTPS / farstad.se
          |
          v
Browser / installed PWA
          |
          |-- Resend magic-link e-mail
          `-- Web Push
```

## Authentication architecture

### Turf identity

Turf's numeric user ID is the stable external identity. Registration begins with the e-mail address already associated with the Turf account.

TurfRadar submits:

```json
[{"email":"user@example.com"}]
```

to `POST /v6/users`. A successful lookup returns the Turf profile including `id` and `name`. An unknown address returns `[]`.

TurfRadar does not need Turf to reveal a user's e-mail by ID. The e-mail is supplied by the registering user and is verified by delivery of the magic link to that same address.

### Magic-link verification

`POST /api/register`:

- validates the Turf account using the submitted e-mail;
- upserts the local TurfRadar user;
- creates/updates `user_auth`;
- creates a cryptographically random verification token;
- stores only its SHA-256 hash in `auth_tokens`;
- stores only the SHA-256 hash of the client login challenge in `auth_challenges`;
- sends the raw verification token only inside the Resend magic link.

Verification tokens expire after 15 minutes and are single-use.

### Why challenge/claim exists

Safari and an installed iOS Home Screen PWA must not be assumed to share cookie storage. A magic link may therefore be verified in Safari while the TurfRadar PWA remains unauthenticated.

TurfRadar solves this with a client-owned login challenge:

```text
PWA generates challenge
       |
       v
POST /api/register
       |
       +--> magic link --> Safari --> /api/auth/verify
       |                          marks challenge verified
       |
       `--> PWA polls /api/auth/claim with original challenge
                                  |
                                  v
                         session cookie set in PWA
```

The raw challenge lives only in the originating client's local storage and request payloads. PostgreSQL stores only its hash.

### Sessions

A successful challenge claim creates a cryptographically random session token.

- Browser receives raw token in cookie `turfradar_session`.
- Cookie attributes: `HttpOnly`, `Secure`, `SameSite=Lax`, path `/turfradar`.
- PostgreSQL stores only SHA-256 of the token in `user_sessions.session_hash`.
- Current session lifetime: 30 days.
- `last_seen_at` is updated when the session is used.
- Logout deletes the server session and the browser cookie.

`get_current_user()` is the common backend identity boundary. Protected user endpoints derive the local user from the valid session and require a verified e-mail.

## Authentication tables

### `user_auth`

Permanent link between `users.id` and the verified registration e-mail.

Key fields:

- `user_id`
- `email`
- `email_verified_at`
- timestamps

### `auth_tokens`

Short-lived, hashed, one-time magic-link tokens.

Key fields:

- `user_id`
- `token_hash`
- `expires_at`
- `used_at`

### `user_sessions`

Authenticated browser/PWA sessions.

Key fields:

- `user_id`
- `session_hash`
- `expires_at`
- `created_at`
- `last_seen_at`

### `auth_challenges`

Temporary bridge between the PWA that initiated login and the browser that opened the magic link.

Key fields:

- `user_id`
- `challenge_hash`
- `verified_at`
- `claimed_at`
- `expires_at`

## User-scoped API rule

The central user endpoints must not accept a Turf ID as an authorization mechanism.

The following flows are session-scoped:

- radar result;
- radius and radar-enabled settings;
- push-subscription registration.

This prevents one authenticated user from selecting another user's data merely by changing a query parameter.

## Workers and multi-user behavior

### `location-worker`

Polls `/v6/users/location` every 30 seconds. Every registered TurfRadar user found in the feed gets their latest latitude, longitude, PostGIS point and observation timestamp updated. Absence from the feed preserves the last-known position.

### `takeover-worker`

Polls the takeover feed every 60 seconds with a two-minute overlap. It upserts zone ownership and records observed opponent history for registered users in `user_taken_players`.

History collection is independent of `radar_enabled`.

### `round-worker`

Polls round metadata every 600 seconds. On a real round transition it clears current-owner state, resets the takeover checkpoint to the new round start and lets the live feed rebuild ownership from a known baseline.

### `radar-worker`

Runs every 30 seconds for users where `radar_enabled = TRUE`. PostGIS performs radius filtering and distance calculation. Current unikaturfare filtering LEFT JOINs zone owners against `user_taken_players`.

## Database design principles

- Turf zone IDs remain `zones.id`.
- Turf user IDs remain stable external identity in `users.turf_user_id`.
- Local `users.id` is used as the application FK for auth, sessions, history and push subscriptions.
- Geographic data uses `GEOGRAPHY(POINT, 4326)`.
- `ST_DWithin` performs radius filtering.
- `ST_Distance` returns distance in metres.
- Medal occurrences are preserved rather than deduplicated.
- `radar_enabled` controls active radar/notification behavior only.
- NULL current owner from the mid-round bootstrap is not guaranteed neutral until a known round reset establishes the baseline.

## Frontend architecture

`frontend/` is source of truth. `deploy.sh` copies it to `/var/www/turfradar/`.

Current separation:

- `index.html`: semantic markup.
- `styles.css`: presentation.
- `app.js`: client state, auth/challenge polling, radar, settings, push and refresh.
- `manifest.webmanifest`: install metadata.
- `service-worker.js`: lifecycle, Web Push and notification-click behavior.

Authentication client state:

- session identity is server-side/cookie based;
- pending PWA login challenge is stored temporarily in `localStorage`;
- dashboard auto-refresh preference is browser-local;
- settings-panel visibility is browser-local.

The service worker does not currently implement an application Cache API/offline cache strategy.

## Web Push

Flow:

```text
PWA
 -> notification permission
 -> GET public VAPID key
 -> PushManager.subscribe()
 -> POST /api/push/subscribe
 -> session identifies owning TurfRadar user
 -> PostgreSQL push_subscriptions

server
 -> pywebpush + VAPID private key
 -> push endpoint
 -> service worker push event
 -> native notification
```

Push delivery has been verified on an installed iPhone PWA while TurfRadar is closed.

## Poll/sync intervals

- Takeover feed: 60 s.
- Takeover safety overlap: 2 min.
- User location: 30 s.
- Radar scan: 30 s.
- Round check: 600 s.
- Optional dashboard auto-refresh: 30 s.
- Auth challenge claim polling during login: 3 s.
- `/zones/all`: manual/not currently scheduled and must respect its upstream rate limit.

## Future layers

### V1

Reliable multi-user radius radar, verified onboarding, useful aggregated opportunity notifications, notification cooldown/history, and backup/restore discipline.

### V2

Use successive positions to infer movement direction/speed and emphasize opportunities ahead of the player.

### V3

Destination/routing corridor and estimated detour time, potentially using an OpenStreetMap routing engine such as OSRM or Valhalla.
