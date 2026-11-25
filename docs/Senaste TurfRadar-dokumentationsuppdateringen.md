# TurfRadar - Session update 2026-11-25

This note captures the changes made after the main documentation checkpoint.

## New: observed take history / unikaturfare state

A new table was added:

`user_taken_players`

Purpose: maintain the set of Turf players a registered TurfRadar user has been observed taking a zone from.

Important fields:

- `user_id` - local TurfRadar user
- `opponent_turf_id` - Turf ID of the previous zone owner
- `opponent_name`
- `first_observed_at`
- `last_observed_at`
- `observed_take_count`

Primary identity is `(user_id, opponent_turf_id)`.

`observed_take_count` means only takes observed by TurfRadar. It is not claimed to be the player's complete historical number of takes.

### Takeover integration

`takeover_worker.py` now inspects each takeover event after updating the zone.

When:

- `currentOwner` belongs to a registered TurfRadar user,
- `previousOwner` exists, and
- current and previous owner IDs are different,

TurfRadar UPSERTs the previous owner into `user_taken_players`.

This collection is independent of `radar_enabled`. Turning radar notifications off must not stop history collection.

A bug was found immediately after adding this: the default psycopg cursor returns tuples, but the first implementation attempted `user["id"]`. It was fixed to use `user[0]`. The transaction/checkpoint design prevented the failed batch from being silently skipped.

## Verified live take-history behavior

Temporary test user:

- Turf name: `H3nkm4n`
- Turf ID: `438929`

TurfRadar followed the user through `/v6/users/location` while the player was actively moving.

Observed examples written automatically to `user_taken_players`:

| Opponent Turf ID | Name | Observed takes |
|---:|---|---:|
| 448488 | Tomte-nisse | 1 |
| 327467 | Ocho | 2 |
| 136818 | foxxy | 1 |

The `Ocho` result verified that repeated takes update the existing opponent record and increment `observed_take_count` rather than creating duplicate opponent rows.

## New: live unikaturfare filtering in radar worker

`radar_worker.py` now LEFT JOINs nearby zone owners against `user_taken_players`.

A nearby zone owner is treated as a current unique-player opportunity when:

1. the zone has a known current owner,
2. the current owner is not the radar user, and
3. there is no matching `(user_id, opponent_turf_id)` in `user_taken_players`.

The radar logs unique-player opportunities separately.

Verified output during live testing:

- `blodyx`: 433 zones within 5000 m, 243 currently classified as unique-player opportunities.
- `H3nkm4n`: 153 zones within 2000 m, 63 currently classified as unique-player opportunities.

Important limitation: `blodyx` has not yet had historical taken-player data imported, so the current "unique" result for that account really means "not observed by TurfRadar since collection began", not "never taken historically".

For a newly observed/test account the same limitation applies until a historical baseline exists.

## Verified per-player unique-owner query

A grouped query was tested that shows one row per nearby current owner rather than one row per zone, including:

- Turf owner ID
- owner name
- number of nearby zones owned
- distance to nearest owned zone

For `H3nkm4n`, the query produced real candidates such as:

- Possanzini - 3 nearby zones, nearest 591 m
- Paddington - 11 nearby zones, nearest 755 m
- LauraPalmer - 3 nearby zones, nearest 934 m
- Lindhardt - 9 nearby zones, nearest 1563 m

This is probably the correct conceptual level for unikaturfare notifications: notify about a player/opportunity, not every zone owned by that player.

Expected live behavior is now:

`unique nearby owner -> user takes a zone from owner -> takeover_worker records opponent -> next radar cycle removes all that owner's zones from unique opportunities`

The final disappearance was not visually observed during this session because the moving test player stopped playing, but every participating subsystem was verified independently and the filtering query is live.

## Location feed live-motion validation

`H3nkm4n` was used to verify that `/v6/users/location` changes frequently enough to support later direction-aware radar.

Two observations about 30 seconds apart changed from approximately:

- `59.342400, 18.056405`
- to `59.342567, 18.055903`

This confirmed real movement flowing through:

`Turf -> /v6/users/location -> location-worker -> PostgreSQL/PostGIS`

V2 may later store a small rolling position history to infer movement direction and speed. Long-term GPS history is not required for that feature.

## PWA branding update

The custom TurfRadar radar/explorer icon is now used as the PWA identity. It should also be used in the dashboard header rather than relying only on the radar emoji.

PWA and push behavior remain verified on iPhone.

## Current ownership data growth

A database health check later in the session showed:

- total zones: `157498`
- zones with known owners: `10644`
- currently unknown owner state: `146854`
- distinct known current owners: `1671`
- latest takeover stored: `2026-11-25 22:04:53+00`

Compared with the early checkpoint of 157496 total zones and 1809 known owners, the background ingestion had discovered 2 additional zones and expanded known owner coverage substantially while the system otherwise remained effectively idle in CPU/RAM terms.

## Documentation corrections / design rules

The core documentation should now explicitly include:

1. `user_taken_players` as the canonical observed opponent-history table.
2. Historical imports, when found, should bootstrap the same table instead of creating a parallel history model.
3. `radar_enabled` must only control active radar/push behavior, never take-history collection.
4. "Unique" is only semantically trustworthy when a user's historical baseline is trustworthy.
5. Opportunity aggregation should be player-level where sensible. One player owning eleven nearby zones should generally produce one useful opportunity, not eleven notifications.
6. Notification history/cooldown/grouping remains the next protection needed before the live unique-player radar is connected to automatic Web Push.

## Immediate next steps

Recommended next sequence:

1. Merge this update into `docs/STATUS.md` and `docs/ARCHITECTURE.md`.
2. Commit migration 008 and the corrected takeover/radar workers.
3. Add notification-history/cooldown tables.
4. Aggregate nearby opportunities per owner and push one useful notification per player/opportunity.
5. Find/import historical taken-player data for `blodyx` into `user_taken_players`.
6. Implement automated off-server PostgreSQL backup and test restore.
