# TurfRadar - Status

Last updated: 2026-11-26

## Goal

TurfRadar is a mobile-first PWA that passively watches Turf and alerts a player when an actionable Turf opportunity appears near the player's latest known position.

V1 remains intentionally basic. Routing, movement direction and advanced medal logic must not block the core radar.

## Current checkpoint

Working and verified:

- Ubuntu 24.04 LTS / Docker Compose on a Contabo VPS.
- PostgreSQL 17 + PostGIS 3.5 with persistent Docker volume.
- Full Turf v6 zone bootstrap and incremental takeover ingestion.
- Turf round tracking and automatic owner reset at round transition.
- Live registered-user location tracking.
- V6 profile and medal sync.
- Observed taken-player history in `user_taken_players`.
- Live unikaturfare filtering in the radar worker.
- FastAPI behind Caddy/HTTPS at `https://farstad.se/turfradar/`.
- Installable iPhone PWA.
- Web Push delivery verified while the PWA is closed.
- E-mail based self-service onboarding using the Turf v6 user lookup.
- Magic-link e-mail delivery through Resend.
- Hashed one-time verification tokens.
- 30-day server sessions stored as hashed session tokens.
- PWA-safe challenge/claim login flow to handle Safari and Home Screen storage isolation.
- Session-based `/api/radar`, `/api/settings` and push-subscription ownership.
- Login, logout and re-login verified end-to-end on iPhone.
- Frontend split into `index.html`, `styles.css` and `app.js`.
- Settings panel can be collapsed and remembers its state locally.

## Authentication and onboarding

The original development API defaulted to Turf user ID `28449`. That design is no longer the intended user identity mechanism.

Current onboarding flow:

1. The client generates a cryptographically random login challenge.
2. User enters the e-mail address registered with Turf.
3. `POST /api/register` looks up the e-mail through Turf `POST /v6/users`.
4. Turf returns the stable Turf user ID and Turf name when the e-mail is valid.
5. TurfRadar creates/updates the local user and authentication identity.
6. TurfRadar stores hashes of both the verification token and login challenge.
7. Resend mails a 15-minute magic link to the submitted address.
8. `GET /api/auth/verify` marks the e-mail and matching pending challenge as verified.
9. The originating PWA polls `POST /api/auth/claim` with its challenge.
10. A verified, unclaimed, unexpired challenge creates a 30-day session in that PWA's own cookie store.
11. The browser receives `turfradar_session` as `HttpOnly`, `Secure`, `SameSite=Lax` with path `/turfradar`.

The PWA challenge/claim step is required because an installed iOS Home Screen web app may use storage isolated from Safari. The magic-link browser and the installed PWA must not be assumed to share a cookie store.

Logout deletes the server-side session and removes the cookie.

## Authentication database tables

Added after the original migration 008 checkpoint:

- `009_create_user_auth.sql`
  - `user_auth`
  - `auth_tokens`
- `010_create_user_sessions.sql`
  - `user_sessions`
- `011_create_auth_challenges.sql`
  - `auth_challenges`

Security rules:

- Raw verification tokens are never stored in PostgreSQL.
- Raw session tokens are never stored in PostgreSQL.
- Raw login challenges are never stored in PostgreSQL.
- SHA-256 hashes are stored instead.
- Verification links are single-use and expire after 15 minutes.
- Login challenges are single-use and expire after 15 minutes.
- Login sessions currently expire after 30 days.

## Turf identity lookup

`POST https://api.turfgame.com/v6/users` was verified to accept an e-mail lookup:

```json
[
  {"email": "user@example.com"}
]
```

A valid Turf account returns the normal user profile including stable numeric `id` and `name`. An unknown e-mail returned an empty array `[]` during testing.

The API did not expose the e-mail address when queried by Turf ID. This is desirable for the current onboarding design: a user must already know and submit the address associated with the Turf account.

## V1 opportunity model

Planned opportunity types:

- **Unikaturfare**: current zone owner is a player the user has never taken a zone from.
- **Untaken zone**: zone has never been taken by the user.
- **Untaken region**: zone belongs to a region in which the user has never taken a zone.
- **Combined opportunity**: multiple valuable properties at the same location should be combined and prioritized.

Live unikaturfare state is based on `user_taken_players`. Until historical data is imported, "unique" means not observed by TurfRadar since collection began, not guaranteed never taken historically.

## Frontend / PWA

Current frontend source files:

- `frontend/index.html` - semantic page structure only.
- `frontend/styles.css` - application styling.
- `frontend/app.js` - auth, radar, settings, push, refresh and PWA client logic.
- `frontend/manifest.webmanifest`.
- `frontend/service-worker.js`.
- `frontend/icons/`.

The service worker currently does not implement an application Cache API strategy. It handles activation, Web Push and notification-click behavior. Browser/WebKit cache can still briefly make recently deployed frontend changes appear stale; a reload/restart resolved this during testing.

## Multi-user state

The database and workers were already largely multi-user capable before onboarding was added:

- `users` uses local `id` plus unique stable `turf_user_id`.
- `location-worker` tracks every registered user appearing in `/v6/users/location`.
- `takeover-worker` records observed opponent history for registered users.
- `radar-worker` scans users with `radar_enabled = TRUE`.
- `push_subscriptions` belongs to the local user and can support multiple device endpoints.

The central HTTP user flows now derive identity from the authenticated session rather than a caller-supplied Turf ID.

## Current next steps

Recommended order:

1. Test onboarding and normal operation with a second real TurfRadar user.
2. Verify push subscription ownership with two different authenticated users/devices.
3. Add notification history/cooldown/grouping before automatic opportunity pushes.
4. Aggregate unikaturfare opportunities by owner/player rather than one notification per zone.
5. Find/import historical taken-player data into `user_taken_players` when a reliable source exists.
6. Add untaken-zone and untaken-region history when a reliable source exists.
7. Implement automated off-server PostgreSQL backup and a tested restore procedure.
8. Add stale push-subscription cleanup for 404/410 responses.

## Parked / later

- Medal-aware opportunity rules.
- Direction-aware radar.
- Route-aware radar.
- Historical zone/region imports without a trustworthy source.
