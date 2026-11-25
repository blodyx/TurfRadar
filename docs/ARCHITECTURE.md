# TurfRadar Architecture

## Purpose

TurfRadar is a proximity and notification engine for Turf. It maintains a local model of the Turf world, watches known users, performs spatial searches with PostGIS, and eventually classifies nearby zones as actionable opportunities.

V1 deliberately optimizes for correctness, simple operations and useful push notifications rather than advanced routing or statistics.

## High-level flow

```text
Turf API v6
├── GET  /zones/all
├── GET  /feeds/takeover?afterDate=...
├── GET  /rounds
├── POST /users
└── GET  /users/location
        |
        v
PostgreSQL 17 + PostGIS 3.5
        |
        +--> takeover worker
        +--> round worker
        +--> location worker
        +--> radar worker
        +--> user sync
        |
        v
FastAPI on 127.0.0.1:8000
        |
        v
Caddy / HTTPS / farstad.se
        |
        +--> Mobile dashboard / PWA
        +--> Web Push subscription
        |
        v
Installed iPhone/Android PWA + notifications
```

## Server

Current deployment is a Contabo VPS running Ubuntu 24.04 LTS.

Observed development host capacity:

- approximately 8 GB RAM
- current service workload well below 1 GB used during normal testing
- CPU/load effectively idle under the present stack

The current scale therefore has large headroom. Infrastructure scaling is not a present constraint.

## Docker services

### `db`

PostgreSQL 17 with PostGIS 3.5.

Persistent data is stored in the named Docker volume `turfradar_db`.

PostgreSQL port 5432 is not published to the internet.

### `api`

FastAPI service using Uvicorn.

Host binding:

```text
127.0.0.1:8000 -> container:8000
```

Only Caddy exposes the API publicly.

API also receives read-only mounts for VAPID key PEM files from `./secrets/`.

### `worker`

Takeover worker.

Responsibilities:

- Poll Turf takeover feed every 60 seconds.
- Read a persistent checkpoint.
- Request events with a two-minute overlap.
- UPSERT current zone metadata/ownership.
- Advance checkpoint to latest event.

### `round-worker`

Polls Turf round metadata every 600 seconds.

On a round transition it:

1. Clears all current owner fields.
2. Clears last-taken state associated with prior-round ownership.
3. Updates current-round checkpoint.
4. Resets takeover checkpoint to new round start.

Takeover worker subsequently rebuilds owner state.

### `location-worker`

Polls visible Turf user locations every 30 seconds.

For registered/watched users that are currently in the location feed it updates:

- latitude
- longitude
- PostGIS geography point
- `position_updated_at`

If a user is absent from the feed, the last known position is retained.

The worker should continue collecting position/profile state even when radar notifications are disabled.

### `radar-worker`

Runs every 30 seconds.

For users with `radar_enabled = TRUE`, performs the proximity query against PostGIS using each user's configured radius.

At the current stage it is primarily the server-side radar/proximity engine. Opportunity classification and notification cooldown/grouping are next.

### User sync

V6 user profile data is retrieved through `/v6/users`.

Profile/medal collection is conceptually independent of `radar_enabled`. Turning radar off must not create gaps in later historical state.

## Data sources

### Full Turf world

`GET /v6/zones/all`

Provides the base zone registry including stable Turf zone IDs, coordinates, region/area metadata and zone statistics.

The endpoint is rate limited to one request per 30 minutes and should use compressed transfer.

A full import of approximately 157k zones took roughly 33 seconds during development.

### Incremental ownership

`GET /v6/feeds/takeover?afterDate=...`

The feed naturally carries repeated/overlapping data. TurfRadar intentionally uses a two-minute overlap and idempotent UPSERTs rather than trying to eliminate every duplicate before database processing.

### Round boundaries

`GET /v6/rounds`

The active round is the latest round whose start timestamp is not in the future.

The round start timestamp is sufficient as V1 round identity.

### Users

`POST /v6/users`

Input is JSON array lookup by name, ID or other supported keys.

TurfRadar uses stable numeric Turf user IDs after lookup.

### Location

`GET /v6/users/location`

The feed does not provide a separate source timestamp. TurfRadar therefore stores the time at which TurfRadar observed the position.

Position age informs UI/quality decisions but does not hard-disable proximity results.

## Database design principles

### Use Turf IDs where stable

Zone identity:

```text
zones.id = Turf zone ID
```

User identity:

```text
users.turf_user_id = Turf user ID
```

Avoid adding meaningless internal IDs for Turf-native entities unless required for future multi-source support.

### Geography

Zone/user locations use:

```text
GEOGRAPHY(POINT, 4326)
```

PostGIS performs spatial work:

- `ST_DWithin()` for radius filtering
- `ST_Distance()` for metres-to-zone

This replaces custom GPS distance math.

### User radar state versus historical collection

`radar_enabled` means:

> Should TurfRadar actively run radar/notification behavior for this user?

It must not mean:

> Stop collecting profile, medal, location or future history data.

Otherwise turning notifications off would create false "unique" opportunities later.

### Medal occurrences are not a set

The `/v6/users` medal list may contain duplicate medal IDs. These repetitions carry information. For example `blodyx` had medal ID 24 twelve times.

`user_medals` therefore stores occurrences rather than deduplicating medal IDs.

### Owner NULL state

During the current mid-round development bootstrap, NULL owner does not reliably mean neutral. It may only mean that TurfRadar has not observed that zone in the takeover feed yet.

After a known new round reset, all zones start from a known neutral baseline. From that point ownership can be rebuilt reliably from takeover events.

This transitional problem is intentionally not over-engineered because no production users are planned before the next round start.

## Frontend/PWA architecture

Static frontend files live in `frontend/` and are deployed to:

```text
/var/www/turfradar/
```

Caddy serves `/turfradar/*` statically and reverse-proxies `/turfradar/api/*` to FastAPI.

`frontend/` is the source of truth. `/var/www/turfradar/` is only deployed output.

PWA components:

- manifest
- service worker
- app icons
- Apple touch icon
- Home Screen standalone mode

The service worker handles the Web Push event and notification click navigation.

## Web Push

Flow:

```text
PWA
 -> request Notification permission
 -> fetch public VAPID key
 -> PushManager.subscribe()
 -> POST subscription to TurfRadar API
 -> PostgreSQL push_subscriptions

server
 -> pywebpush
 -> VAPID private key
 -> browser push endpoint
 -> service worker push event
 -> native notification
```

Push delivery was verified on an installed iPhone PWA while the TurfRadar app was closed.

The private VAPID key never belongs in Git or frontend code.

## Poll/sync intervals

Current values:

| Process | Interval / rule |
|---|---|
| Takeover feed | 60 s |
| Takeover overlap | 2 min |
| User location | 30 s |
| Radar scan | 30 s |
| Round check | 600 s |
| Dashboard auto-refresh | optional 30 s, browser-local |
| `/zones/all` | manual/currently not scheduled; never more often than API allows |

## Future architecture layers

### V1

Radius radar based on latest known position.

### V2

Use successive positions to infer speed/direction and emphasize zones ahead of the user.

### V3

Destination/routing corridor, candidate filtering and estimated real detour time, potentially using an OpenStreetMap routing engine such as OSRM or Valhalla.

Routing must remain a later optimization and must not complicate V1.
