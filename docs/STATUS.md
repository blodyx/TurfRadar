# TurfRadar - Status

Last updated: 2026-11-25

## Goal

TurfRadar is a mobile-first PWA that passively watches Turf and alerts a player when an actionable Turf opportunity appears near the player's latest known position.

V1 remains intentionally basic. Routing, movement direction and advanced medal logic must not block the core radar.

## V1 opportunity model

Planned opportunity types:

- **Unikaturfare**: current zone owner is a player the user has never taken a zone from.
- **Untaken zone**: zone has never been taken by the user.
- **Untaken region**: zone belongs to a region in which the user has never taken a zone.
- **Combined opportunity**: multiple valuable properties at the same location should be combined and prioritized.

Later versions may include medal-aware, attribute-aware, directional and route-aware opportunities.

## Infrastructure

- VPS provider: Contabo
- OS: Ubuntu 24.04 LTS
- Host resources observed: about 8 GB RAM, very low CPU/load under current TurfRadar workload
- Public site: `https://farstad.se/turfradar/`
- Git repository: `blodyx/TurfRadar`
- Docker + Docker Compose
- Caddy for HTTPS and reverse proxy
- PostgreSQL 17 + PostGIS 3.5
- Persistent Docker volume for PostgreSQL
- GitHub authentication from server via SSH key

## Running services

Current Compose services:

- `db` - PostgreSQL/PostGIS
- `api` - FastAPI, bound to `127.0.0.1:8000`
- `worker` - takeover feed worker
- `round-worker` - Turf round monitor/reset worker
- `location-worker` - watched-user location worker
- `radar-worker` - proximity radar worker

Services use `restart: unless-stopped`.

## Turf zone state

A full v6 bootstrap loaded approximately 157k Turf zones. After import the database contained **157,496 zones**.

`zones.id` is the Turf zone ID and is the table primary key.

Spatial queries are verified:

- `ST_DWithin()` correctly finds zones inside a user radius.
- `ST_Distance()` returns useful distance in metres.
- GiST index exists on `zones.location`.

A real test from `blodyx`'s live Turf position found **121 zones within 2,000 m** and at that time **78 had a known current owner**.

## Turf API v6 integrations

### Full zones

`GET https://api.turfgame.com/v6/zones/all`

Used for full zone bootstrap/sync.

Known behavior:

- Returns all zones.
- Contains stable zone IDs and geographic/region metadata.
- Send `Accept-Encoding: gzip` / use compressed transfer.
- Only one request per 30 minutes is allowed.
- The list updates at least hourly.

### Takeover feed

`GET https://api.turfgame.com/v6/feeds/takeover`

Uses optional `afterDate`.

Current worker behavior:

1. Read `last_takeover_time` from `system_state`.
2. Subtract two minutes for a safety overlap.
3. Request only events newer than that timestamp.
4. UPSERT zones by Turf zone ID.
5. Store the newest observed event time.
6. Sleep 60 seconds.

The overlap is safe because the operation is idempotent by zone ID.

### Rounds

`GET https://api.turfgame.com/v6/rounds`

Current round is selected as the latest round whose `start <= now`.

Observed data while developing:

- November round start: `2026-11-01T11:00:00+0000`
- December round start: `2026-12-06T11:00:00+0000`

At a detected round change:

1. `current_owner_id` is cleared.
2. `current_owner_name` is cleared.
3. `date_last_taken` is cleared.
4. `current_round_start` is updated.
5. `last_takeover_time` is set to the new round start.
6. The takeover worker rebuilds owner state from the new round.

### Users

`POST https://api.turfgame.com/v6/users`

Verified for Turf user `blodyx`:

- Turf user ID: `28449`
- `uniqueZonesTaken`: `2285`
- `taken`: `51310`
- region: `127 / Västerbotten`
- `zones` represents zones currently owned by the user
- `medals` can contain repeated medal IDs

Medal ID `24` appeared 12 times for `blodyx`, reflecting repeatable event-medal occurrences. TurfRadar therefore preserves medal occurrences rather than deduplicating them.

### User locations

`GET https://api.turfgame.com/v6/users/location`

Returns users currently represented on the Turf map with `id`, `name`, `latitude` and `longitude`.

Verified `blodyx` position during development:

- latitude `63.825998`
- longitude `20.304683`

When a watched user disappears from the feed, TurfRadar retains the last known position instead of clearing it.

Position age is metadata/quality information, not a hard blocker for the radar.

## Database

### `zones`

Important fields:

- Turf zone ID primary key
- name
- latitude / longitude
- `location GEOGRAPHY(POINT, 4326)`
- current owner ID/name
- region ID/name
- area ID/name
- country
- zone type ID/name
- points per hour
- takeover points
- total takeovers
- creation date
- last-taken date
- updated timestamp

### `system_state`

Persistent worker checkpoints/state.

Known keys:

- `last_takeover_time`
- `current_round_start`

### `users`

Contains:

- internal ID
- Turf user ID/name
- `radar_enabled`
- radius
- last known lat/lon/PostGIS point
- `position_updated_at`
- country/region
- unique-zone count
- total takes
- rank and total points
- profile update timestamp

Current developer/test user:

- `blodyx`
- Turf ID `28449`

`radar_enabled` must only control radar/notification behavior. Profile, medal, location and future history collection must not be disabled by this flag.

### `user_medals`

Stores each medal occurrence separately.

The tuple effectively includes:

- local user ID
- medal ID
- occurrence number

This intentionally preserves repeated event medals.

### `push_subscriptions`

Stores one Web Push subscription per browser/device endpoint:

- local user ID
- endpoint
- p256dh key
- auth key
- timestamps

A user may later have multiple devices/subscriptions.

## API and frontend

FastAPI is reachable through Caddy at `/turfradar/api/...`.

Verified backend functions include:

- health
- radar result
- server-side radius updates
- server-side radar enabled/disabled state
- VAPID public key
- push subscription registration

The mobile dashboard currently shows:

- TurfRadar identity
- Turf username
- last-known-position age
- radius
- number of nearby zones
- number with known owner
- nearest zones, owners and distances
- radius buttons: 500 m / 1 km / 2 km / 5 km
- radar on/off
- auto-refresh on/off
- manual refresh
- dashboard refreshed timestamp
- Web Push activation

Auto-refresh is browser-local state and defaults to a 30-second cycle when enabled.

## PWA and Web Push

TurfRadar is installable as a PWA from an iPhone Home Screen.

PWA assets include:

- `manifest.webmanifest`
- `service-worker.js`
- 192x192 app icon
- 512x512 app icon
- 180x180 Apple touch icon

Brand icon: an original Turf-like walking/explorer figure inside classic radar rings, on TurfRadar's dark background.

Web Push has been verified end-to-end on iPhone:

1. Installed Home Screen PWA requested notification permission.
2. Browser push subscription was stored in PostgreSQL.
3. Server sent a signed Web Push using VAPID.
4. iPhone displayed the notification even when TurfRadar was closed.

VAPID private/public PEM files are stored under `secrets/` and ignored by Git.

## Current ownership caveat

TurfRadar was bootstrapped in the middle of an existing Turf round. Therefore a NULL `current_owner_id` currently means "not known by TurfRadar" and must not yet be treated as guaranteed neutral.

This is intentionally parked. There are no production users before the next round start. At the next known round reset TurfRadar clears all owners from a known neutral baseline and then rebuilds owner state from takeover events.

## Deliberately parked

- Import of historical taken opponents / unikaturfare history
- Import of historical unique zones
- Historical regions taken
- Opportunity scoring and grouping
- Notification history/cooldown
- Medal opportunity rules
- Direction-aware radar
- Route-aware radar
- Multi-user authentication/account onboarding

## Next steps

Recommended order:

1. Build notification history and cooldown/grouping.
2. Connect opportunity/radar results to Web Push without notification spam.
3. Find a robust history import/source for previously taken opponents.
4. Add untaken-zone and untaken-region history when a suitable source exists.
5. Automate full `/zones/all` refresh safely around its 30-minute rate limit.
6. Implement automatic PostgreSQL backups and test restore.
