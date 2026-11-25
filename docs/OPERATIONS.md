# TurfRadar Operations

## Environment

Current host:

- Provider: Contabo
- Ubuntu 24.04 LTS
- Docker Engine + Docker Compose
- Caddy installed as a host service
- PostgreSQL/PostGIS runs in Docker
- Application repository under the `blodyx` user

Public URL:

```text
https://farstad.se/turfradar/
```

API is proxied through `/turfradar/api/`.

## SSH

Connect using the `blodyx` account and SSH credentials configured for the VPS.

Project directory:

```bash
cd ~/TurfRadar
```

## Normal deployment

Run:

```bash
./deploy.sh
```

Expected deploy behavior:

1. Validate Docker Compose.
2. Build/start Compose services.
3. Copy the complete `frontend/` tree to `/var/www/turfradar/`.
4. Normalize deployed file permissions.
5. Print Compose service status.

`frontend/` in Git is the source of truth. `/var/www/turfradar/` is disposable/deployed output.

## Docker service status

```bash
docker compose ps
```

Expected services:

```text
api
db
location-worker
radar-worker
round-worker
worker
```

## Logs

### Takeovers

```bash
docker compose logs -f worker
```

Expected pattern:

```text
Received N takeover events after <timestamp>
Upserted N takeover events
```

### User locations

```bash
docker compose logs -f location-worker
```

Expected pattern:

```text
Location feed: N visible players, updated M watched users
```

### Radar

```bash
docker compose logs -f radar-worker
```

Expected development pattern:

```text
Radar blodyx: N zones within X m, Y currently owned
```

### Rounds

```bash
docker compose logs -f round-worker
```

Typical state:

```text
Round unchanged: <name> (<start>)
```

## Database shell

```bash
docker compose exec db \
  psql -U turfradar -d turfradar
```

Useful checks:

### Number of zones

```sql
SELECT COUNT(*) FROM zones;
```

Development checkpoint after full sync:

```text
157496
```

### User position

```sql
SELECT
    turf_user_id,
    turf_name,
    latitude,
    longitude,
    position_updated_at,
    NOW() - position_updated_at AS position_age,
    radius_m,
    radar_enabled
FROM users;
```

### Worker state

```sql
SELECT * FROM system_state;
```

Known keys:

```text
last_takeover_time
current_round_start
```

### Push subscriptions

```sql
SELECT
    ps.id,
    u.turf_name,
    ps.created_at,
    ps.updated_at
FROM push_subscriptions ps
JOIN users u ON u.id = ps.user_id;
```

Avoid printing full push endpoints/keys unnecessarily.

## Manual API checks

### Health

```bash
curl -s https://farstad.se/turfradar/api/health
```

### Radar summary

```bash
curl -s https://farstad.se/turfradar/api/radar | \
python3 -m json.tool
```

### Disable radar

```bash
curl -s -X PATCH \
  -H "Content-Type: application/json" \
  -d '{"radarEnabled":false}' \
  https://farstad.se/turfradar/api/settings
```

### Enable radar

```bash
curl -s -X PATCH \
  -H "Content-Type: application/json" \
  -d '{"radarEnabled":true}' \
  https://farstad.se/turfradar/api/settings
```

### Change radius

```bash
curl -s -X PATCH \
  -H "Content-Type: application/json" \
  -d '{"radiusM":2000}' \
  https://farstad.se/turfradar/api/settings
```

## Manual user profile sync

```bash
docker compose run --rm --build worker \
  python -m app.user_sync
```

## Manual full zone sync

The current development sync can consume a local `/tmp/zones-all.json` file mounted read-only into the worker.

The Turf API full-zone endpoint has a 30-minute request limit. Do not repeatedly fetch during testing.

Example controlled fetch:

```bash
curl --compressed \
  -H "Accept-Encoding: gzip" \
  -o /tmp/zones-all.json \
  https://api.turfgame.com/v6/zones/all
```

Then sync using the zone sync module as configured in the container.

Full refresh automation is still TODO and must respect the upstream API limit.

## Caddy

Config file:

```text
/etc/caddy/Caddyfile
```

Validate after changes:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
```

Reload:

```bash
sudo systemctl reload caddy
```

Status:

```bash
systemctl status caddy --no-pager
```

## PWA

Files live under `frontend/` and deploy to `/var/www/turfradar/`.

Important files:

```text
frontend/index.html
frontend/manifest.webmanifest
frontend/service-worker.js
frontend/icons/icon-192.png
frontend/icons/icon-512.png
frontend/icons/apple-touch-icon.png
```

Installed iPhone PWA was verified to run standalone and receive Web Push while closed.

## VAPID / secrets

Host secret files:

```text
secrets/vapid_private.pem
secrets/vapid_public.pem
```

They are mounted read-only into the API container under:

```text
/run/secrets/
```

Rules:

- `secrets/` must be ignored by Git.
- `.env` must be ignored by Git.
- Never expose the private VAPID key to frontend code or API responses.
- Public VAPID key is intentionally exposed through the push public-key endpoint.

Manual push test:

```bash
docker compose exec api python -m app.push_test
```

Verified result: notification reached iPhone even when TurfRadar PWA was closed.

## Git workflow

Typical flow:

```bash
git status
git add ...
git commit -m "..."
git push
./deploy.sh
```

The server uses an SSH key to authenticate to GitHub.

## Round reset behavior

At a real Turf round transition the round worker clears prior owner state and moves the takeover checkpoint to the new round start.

After that, the takeover feed rebuilds owners from a known neutral baseline.

Do not fake a round change in production merely to test reset logic unless a safe test database exists.

## Backup - high-priority TODO

The project intentionally needs stronger backup discipline because earlier hobby-project data has been lost over the years.

Current database persistence in a Docker volume protects against container recreation, but it is **not an off-host backup**.

Implement next:

1. Nightly `pg_dump` of `turfradar`.
2. Store copies outside the VPS.
3. Retention, e.g. 7 daily + 4 weekly + 6 monthly backups.
4. Encrypt backup material if it contains user/push/location data.
5. Document and test a restore into a temporary database/container.
6. Keep VAPID private key and required `.env` secrets in a secure off-server recovery location.

A backup is not considered complete until restore has been tested.

## Security / production TODOs

Before adding external users:

- Add real account/authentication model; current API defaults to the development Turf user.
- Protect write endpoints from arbitrary internet users.
- Add anti-CSRF/auth controls appropriate to the chosen auth scheme.
- Add notification subscription removal/expiry handling.
- Delete stale push subscriptions on 404/410 push responses.
- Add database backup and restore procedure.
- Define retention for location and notification history.
