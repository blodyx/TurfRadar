# TurfRadar

TurfRadar is a mobile-first PWA that monitors the Turf world around a player and is intended to notify the player when something worth acting on appears nearby.

The project started with a deliberately simple V1 idea:

`latest known position -> nearby Turf zones -> opportunity rules -> notification`

## Current state

Working today:

- Ubuntu 24.04 LTS / Docker Compose deployment on a Contabo VPS
- PostgreSQL 17 + PostGIS 3.5
- Full Turf v6 zone bootstrap, about 157,496 zones in the current database
- Incremental takeover ingestion using `/v6/feeds/takeover?afterDate=...`
- Turf round tracking and automatic owner reset at a new round
- Live Turf user location tracking
- V6 user profile and medal sync
- PostGIS radius radar
- FastAPI backend behind Caddy/HTTPS
- Mobile dashboard at `https://farstad.se/turfradar/`
- Server-side radius and radar on/off settings
- Client-side optional 30-second dashboard auto-refresh
- Installable PWA on iPhone
- Web Push subscription and verified push delivery to iPhone even while TurfRadar is closed
- One-command deployment with `./deploy.sh`

## V1 scope

The intended opportunity types are:

1. Unikaturfare: nearby zone owned by a player the user has never taken a zone from.
2. Untaken zone: nearby zone the user has never taken.
3. Untaken region: nearby zone in a region where the user has never taken a zone.
4. Combined opportunities: one location satisfying multiple rules should rank higher and generate one useful notification rather than several.

Historical take/zone/region data is currently parked because there is not yet a clean import source. It must not block the rest of V1.

## Repository layout

```text
TurfRadar/
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
├── database/
├── docs/
│   ├── API.md
│   ├── ARCHITECTURE.md
│   ├── OPERATIONS.md
│   └── STATUS.md
├── frontend/
├── secrets/              # ignored by Git
├── compose.yaml
├── deploy.sh
├── .env                  # ignored by Git
└── README.md
```

## Deploy

From the project directory on the server:

```bash
./deploy.sh
```

The deployment validates Compose, builds/starts the services, deploys the complete frontend to `/var/www/turfradar/`, and prints service status.

## Documentation

- `docs/STATUS.md` - current project checkpoint and next steps
- `docs/ARCHITECTURE.md` - system architecture and design decisions
- `docs/API.md` - Turf v6 endpoints and TurfRadar API
- `docs/OPERATIONS.md` - server operations, deployment, troubleshooting and backup TODOs

## Important design rules

- TurfRadar production logic uses Turf API v6.
- Turf IDs are preserved as the stable external identities for Turf zones and players.
- Position age is recorded and shown, but an old last-known position does not make the radar blind.
- `radar_enabled` controls radar/notifier behavior, not historical/profile data collection.
- `.env` and `secrets/` must never be committed.
- Current-owner NULL values from this mid-round bootstrap must not be assumed to mean neutral until a known round reset establishes a complete baseline.
