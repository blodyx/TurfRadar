# TurfRadar – Status

## Mål

TurfRadar är en PWA/webbtjänst som passivt bevakar Turf och notifierar användaren när något intressant finns i närheten.

V1 ska vara enkel: senaste kända position + vald radie + relevanta Turf-träffar.

## V1 – planerade träfftyper

- Unikaturfare: zon ägs av en spelare användaren aldrig tagit från.
- Otagen zon: zon användaren aldrig tagit.
- Otagen region: zon i region användaren aldrig tagit.
- Kombinerade träffar ska prioriteras högre.

Historiska tagna zoner och regioner saknar för närvarande en bra importkälla och blockerar inte fortsatt utveckling.

## Infrastruktur

- Server: Contabo VPS
- OS: Ubuntu 24.04 LTS
- Repo: blodyx/TurfRadar
- Docker + Docker Compose
- PostgreSQL 17 + PostGIS 3.5
- Persistent Docker-volume för databasen
- GitHub-access från servern via SSH

## Containers

- `db`
  - PostgreSQL/PostGIS
- `worker`
  - inkrementell takeover-feed
  - pollar var 60:e sekund
- `round-worker`
  - kontrollerar aktiv Turf-runda var 10:e minut

Alla använder `restart: unless-stopped`.

## Turf API

### Full zonlista

`GET https://api.turfgame.com/v6/zones/all`

- Returnerar alla zoner.
- Ska hämtas med gzip.
- Max ett anrop per 30 minuter.
- Listan uppdateras minst en gång per timme.
- Senaste bootstrap: cirka 157 000 zoner.
- Databasen innehöll 157 496 zoner efter första full-sync.

Används för statisk/grundläggande zoninformation:
- Turf zone ID
- namn
- lat/lon
- region och area
- land
- zontyp
- PPH
- takeover points
- total takeovers
- creation date

### Takeover-feed

`GET https://api.turfgame.com/v6/feeds/takeover`

Stödjer:

`afterDate=<timestamp>`

Takeover-workern:
1. Läser `last_takeover_time` från `system_state`.
2. Drar av 2 minuter som säkerhetsöverlapp.
3. Hämtar bara nyare events.
4. UPSERT:ar zonerna.
5. Sparar senaste observerade eventtid.

Överlappet är säkert eftersom UPSERT på Turf zone ID är idempotent.

### Rounds

`GET https://api.turfgame.com/v6/rounds`

Aktuell runda identifieras som senaste `start <= now`.

Aktuell observerad runda:
- November
- start: `2026-11-01T11:00:00+0000`

Nästa kända runda:
- December
- start: `2026-12-06T11:00:00+0000`

Vid rundbyte ska round-worker:
1. Nolla `current_owner_id`.
2. Nolla `current_owner_name`.
3. Nolla `date_last_taken`.
4. Uppdatera `current_round_start`.
5. Sätta `last_takeover_time` till nya rundans starttid.
6. Låta takeover-workern återbygga aktuell ägarbild.

### Users

`POST https://api.turfgame.com/v6/users`

Request:

`[{"id": 28449}]`

eller lookup via namn:

`[{"name": "blodyx"}]`

Verifierat för `blodyx`:

- Turf user ID: `28449`
- uniqueZonesTaken: `2285`
- taken: `51310`
- hemregion: `127 / Västerbotten`
- `zones` innehåller zoner användaren äger i aktuell runda
- `medals` innehåller medaljinstanser och kan innehålla samma medalj-ID flera gånger
- medalj 24 förekommer 12 gånger för `blodyx`

### API-princip

TurfRadar använder Turf API v6 för produktionslogik.

Äldre API-versioner ska inte vara beroenden i TurfRadar.

## Databas

### zones

Primärnyckeln är Turf-zonens eget stabila ID:

`zones.id = Turf zone ID`

Ingen separat intern zone-ID används.

Viktiga fält:
- id
- name
- latitude
- longitude
- location `GEOGRAPHY(POINT,4326)`
- current_owner_id
- current_owner_name
- region_id
- region_name
- area_id
- area_name
- country
- zone_type_id
- zone_type_name
- points_per_hour
- takeover_points
- total_takeovers
- date_created
- date_last_taken
- updated_at

GiST-index finns på `location`.

Verifierat:
- `ST_DWithin()` fungerar för radiesökning.
- `ST_Distance()` ger avstånd i meter.

### system_state

Persistent key/value-state.

Aktuella keys:
- `last_takeover_time`
- `current_round_start`

### users

Tabell finns för bevakade användare.

Viktiga fält:
- internt ID
- turf_user_id
- turf_name
- radius_m
- latitude
- longitude
- location
- position_updated_at
- active

Första användare:
- Turf name: `blodyx`
- Turf user ID: `28449`
- default radie: 2000 m

## Verifierat fungerande

- Docker/Compose
- PostgreSQL/PostGIS
- GitHub push över SSH
- full hämtning av alla Turf-zoner
- import/UPSERT av cirka 157k zoner
- geografiska PostGIS-frågor
- takeover-feed
- inkrementell takeover-feed med `afterDate`
- persistent takeover-checkpoint
- automatisk round-detektering
- skydd mot reset när rundan är oförändrad
- round-resetkod
- permanenta background workers

## Medvetet parkerat

- Historiska tagna zoner
- Historiska tagna regioner
- TvT/import av tidigare tagna spelare
- Web Push
- PWA/frontend
- login/autentisering
- Caddy/HTTPS
- medaljlogik
- färdriktningsmedvetenhet
- ruttmedvetenhet

## Versioner

### V1

Basic radius radar.

`senaste position -> zoner inom X meter -> regler -> notifiering`

Ingen routing.

### V2

Rörelseriktning och hastighet.

Radarn tittar längre framför än bakom användaren.

### V3

Destination/ruttkorridor och faktisk uppskattad omväg.

## Nästa steg

**Lös användarens senaste position.**

När positionen finns ska första personliga radarsvepet kunna göras:

`users.location -> ST_DWithin(zones.location, radius_m) -> kandidater`

Därefter byggs opportunity-filtreringen ovanpå resultatet.

Historiska tagna zoner/regioner behöver inte lösas innan själva radarsvepet fungerar.
