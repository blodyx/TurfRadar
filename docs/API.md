# TurfRadar API Reference

This document records the API behavior actually used/verified while building TurfRadar.

## Turf API v6 dependencies

Production logic should use Turf API v6. Older Turf API versions are not production dependencies.

Base URL:

```text
https://api.turfgame.com/v6
```

## Turf: all zones

```http
GET /v6/zones/all
```

Purpose: full Turf zone world/bootstrap.

Important request behavior:

- Use compressed transfer (`Accept-Encoding: gzip`; curl `--compressed` works).
- API allows only one request per 30 minutes.
- Documentation states the list updates at least hourly.

Example response object observed:

```json
{
  "dateCreated": "2026-04-22T22:00:00+0000",
  "id": 786444,
  "latitude": 60.399816,
  "longitude": 5.339665,
  "name": "Kakleklippen",
  "pointsPerHour": 1,
  "region": {
    "area": {
      "id": 3078,
      "name": "Bergen"
    },
    "country": "no",
    "id": 181,
    "name": "Vestlandet"
  },
  "takeoverPoints": 185,
  "totalTakeovers": 0
}
```

The endpoint supplies stable Turf zone IDs and is the correct bulk source for TurfRadar.

## Turf: takeover feed

```http
GET /v6/feeds/takeover
```

Optional query:

```text
afterDate=<URL-encoded timestamp>
```

Only posts newer than `afterDate` are returned.

TurfRadar uses the latest processed timestamp minus two minutes to create deliberate overlap.

Important response data includes:

- event type/time
- zone ID/name/coordinates
- current owner ID/name
- previous owner ID/name
- region/area/country
- zone type if present
- points/statistics

Owner state is UPSERTed by zone ID.

## Turf: rounds

```http
GET /v6/rounds
```

Response includes monthly Turf round start timestamps.

Example:

```json
[
  {
    "name": "November",
    "start": "2026-11-01T11:00:00+0000"
  },
  {
    "name": "December",
    "start": "2026-12-06T11:00:00+0000"
  }
]
```

TurfRadar selects the latest round with `start <= now`.

## Turf: users

```http
POST /v6/users
Content-Type: application/json
```

Lookup can use arrays such as:

```json
[
  {"name": "blodyx"}
]
```

or:

```json
[
  {"id": 28449}
]
```

Verified response for `blodyx` contained:

- `id = 28449`
- `name = blodyx`
- `country = se`
- region `127 / Västerbotten`
- `uniqueZonesTaken = 2285`
- `taken = 51310`
- rank, points and total points
- `zones`: zones currently owned in the active round
- `medals`: medal occurrences, including repeated IDs

Repeated medal IDs are meaningful and must not be automatically deduplicated.

## Turf: current user locations

```http
GET /v6/users/location
```

Returns current players with a location visible on the Turf map.

Observed shape:

```json
{
  "latitude": 63.825998,
  "longitude": 20.304683,
  "name": "blodyx",
  "id": 28449
}
```

No source timestamp is provided in the observed data. TurfRadar records observation time locally.

If a watched user is absent, TurfRadar keeps the previously known position.

---

# TurfRadar HTTP API

Public prefix through Caddy:

```text
https://farstad.se/turfradar/api
```

## Health

```http
GET /api/health
```

Example:

```json
{
  "status": "ok",
  "service": "TurfRadar"
}
```

## Radar

```http
GET /api/radar?turf_user_id=28449
```

The user ID query currently defaults to the development user.

Response shape:

```json
{
  "user": {
    "turfUserId": 28449,
    "name": "blodyx",
    "radiusM": 1000,
    "radarEnabled": true,
    "latitude": 63.825998,
    "longitude": 20.304683,
    "positionUpdatedAt": "...",
    "positionAgeSeconds": 123
  },
  "summary": {
    "zones": 42,
    "ownedZones": 30
  },
  "zones": [
    {
      "id": 7704,
      "name": "MountLily",
      "current_owner_id": 414640,
      "current_owner_name": "Nihilisten",
      "region_id": 127,
      "region_name": "Västerbotten",
      "distance_m": 346
    }
  ]
}
```

The API intentionally still returns dashboard information when `radarEnabled` is false. The flag controls active radar/notification behavior, not whether the UI may inspect state.

## Settings

```http
PATCH /api/settings?turf_user_id=28449
Content-Type: application/json
```

Supported fields:

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

Fields may be changed independently.

Example response:

```json
{
  "radiusM": 2000,
  "radarEnabled": true
}
```

Dashboard auto-refresh is not a server setting; it is stored locally in the browser/PWA.

## Push public key

```http
GET /api/push/public-key
```

Returns the public VAPID application server key in URL-safe Base64 format:

```json
{
  "publicKey": "B..."
}
```

This key is public by design.

## Push subscribe

```http
POST /api/push/subscribe?turf_user_id=28449
Content-Type: application/json
```

Request matches a browser PushSubscription JSON object:

```json
{
  "endpoint": "https://push-service.example/...",
  "keys": {
    "p256dh": "...",
    "auth": "..."
  }
}
```

Subscription is UPSERTed by endpoint and associated with the TurfRadar user.

Response:

```json
{
  "status": "subscribed"
}
```

## Push test helper

A development-only/manual Python module exists to send a Web Push test from inside the API container.

```bash
docker compose exec api python -m app.push_test
```

Do not expose this as an unauthenticated public HTTP endpoint.
