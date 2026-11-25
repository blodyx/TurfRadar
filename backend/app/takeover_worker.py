from datetime import datetime, timedelta

import os
import httpx
import psycopg
import time


TAKEOVER_URL = "https://api.turfgame.com/v6/feeds/takeover"


def get_connection():
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def upsert_zone(cur, event):
    zone = event["zone"]

    owner = zone.get("currentOwner") or event.get("currentOwner")
    region = zone.get("region") or {}
    area = region.get("area") or {}
    zone_type = zone.get("type") or {}

    longitude = zone["longitude"]
    latitude = zone["latitude"]

    cur.execute(
        """
        INSERT INTO zones (
            id,
            name,
            latitude,
            longitude,
            location,
            current_owner_id,
            current_owner_name,
            region_id,
            region_name,
            area_id,
            area_name,
            country,
            zone_type_id,
            zone_type_name,
            points_per_hour,
            takeover_points,
            total_takeovers,
            date_created,
            date_last_taken,
            updated_at
        )
        VALUES (
            %(id)s,
            %(name)s,
            %(latitude)s,
            %(longitude)s,
            ST_SetSRID(
                ST_MakePoint(%(longitude)s, %(latitude)s),
                4326
            )::geography,
            %(owner_id)s,
            %(owner_name)s,
            %(region_id)s,
            %(region_name)s,
            %(area_id)s,
            %(area_name)s,
            %(country)s,
            %(zone_type_id)s,
            %(zone_type_name)s,
            %(points_per_hour)s,
            %(takeover_points)s,
            %(total_takeovers)s,
            %(date_created)s,
            %(date_last_taken)s,
            NOW()
        )
        ON CONFLICT (id)
        DO UPDATE SET
            name = EXCLUDED.name,
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            location = EXCLUDED.location,
            current_owner_id = EXCLUDED.current_owner_id,
            current_owner_name = EXCLUDED.current_owner_name,
            region_id = EXCLUDED.region_id,
            region_name = EXCLUDED.region_name,
            area_id = EXCLUDED.area_id,
            area_name = EXCLUDED.area_name,
            country = EXCLUDED.country,
            zone_type_id = EXCLUDED.zone_type_id,
            zone_type_name = EXCLUDED.zone_type_name,
            points_per_hour = EXCLUDED.points_per_hour,
            takeover_points = EXCLUDED.takeover_points,
            total_takeovers = EXCLUDED.total_takeovers,
            date_created = EXCLUDED.date_created,
            date_last_taken = EXCLUDED.date_last_taken,
            updated_at = NOW()
        """,
        {
            "id": zone["id"],
            "name": zone["name"],
            "latitude": latitude,
            "longitude": longitude,
            "owner_id": owner.get("id") if owner else None,
            "owner_name": owner.get("name") if owner else None,
            "region_id": region.get("id"),
            "region_name": region.get("name"),
            "area_id": area.get("id"),
            "area_name": area.get("name"),
            "country": region.get("country"),
            "zone_type_id": zone_type.get("id"),
            "zone_type_name": zone_type.get("name"),
            "points_per_hour": zone.get("pointsPerHour"),
            "takeover_points": zone.get("takeoverPoints"),
            "total_takeovers": zone.get("totalTakeovers"),
            "date_created": zone.get("dateCreated"),
            "date_last_taken": zone.get("dateLastTaken"),
        },
    )

def record_taken_player(cur, event):
    zone = event["zone"]

    current_owner = (
        zone.get("currentOwner")
        or event.get("currentOwner")
    )

    previous_owner = zone.get("previousOwner")

    if not current_owner or not previous_owner:
        return

    # Samma owner på båda sidor ska inte registreras
    # som en take från en annan spelare.
    if current_owner["id"] == previous_owner["id"]:
        return

    cur.execute(
        """
        SELECT id
        FROM users
        WHERE turf_user_id = %s
        """,
        (current_owner["id"],),
    )

    user = cur.fetchone()

    if not user:
        return

    user_id = user[0]


    cur.execute(
        """
        INSERT INTO user_taken_players (
            user_id,
            opponent_turf_id,
            opponent_name,
            first_observed_at,
            last_observed_at,
            observed_take_count
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            1
        )
        ON CONFLICT (
            user_id,
            opponent_turf_id
        )
        DO UPDATE SET
            opponent_name = EXCLUDED.opponent_name,
            last_observed_at = EXCLUDED.last_observed_at,
            observed_take_count =
                user_taken_players.observed_take_count + 1
        """,
        (
            user_id,
            previous_owner["id"],
            previous_owner["name"],
            event["time"],
            event["time"],
        ),
    )


def get_last_takeover_time(cur):
    cur.execute(
        "SELECT value FROM system_state WHERE key = 'last_takeover_time'"
    )
    row = cur.fetchone()

    if not row:
        return None

    return datetime.fromisoformat(row[0])


def save_last_takeover_time(cur, event_time):
    cur.execute(
        """
        INSERT INTO system_state (key, value, updated_at)
        VALUES ('last_takeover_time', %s, NOW())
        ON CONFLICT (key)
        DO UPDATE SET
            value = EXCLUDED.value,
            updated_at = NOW()
        """,
        (event_time,),
    )

#def main():
#    response = httpx.get(TAKEOVER_URL, timeout=30.0)
#    response.raise_for_status()
#    events = response.json()
#
#    print(f"Received {len(events)} takeover events", flush=True)
#
#    with get_connection() as conn:
##        with conn.cursor() as cur:
#            for event in events:
#                upsert_zone(cur, event)
#
#    print(f"Upserted {len(events)} takeover events", flush=True)

def main():
    with get_connection() as conn:
        with conn.cursor() as cur:
            last_time = get_last_takeover_time(cur)

            params = {}

            if last_time:
                after_time = last_time - timedelta(minutes=2)

                params["afterDate"] = after_time.strftime(
                    "%Y-%m-%dT%H:%M:%S+0000"
                )

            response = httpx.get(
                TAKEOVER_URL,
                params=params,
                timeout=30.0,
            )
            response.raise_for_status()

            events = response.json()

            print(
                f"Received {len(events)} takeover events "
                f"after {params.get('afterDate', 'initial feed')}",
                flush=True,
            )

            newest_time = last_time

            for event in events:
                upsert_zone(cur, event)
                record_taken_player(cur, event)

                event_time = datetime.fromisoformat(
                    event["time"]
                )

                if newest_time is None or event_time > newest_time:
                    newest_time = event_time

            if newest_time:
                save_last_takeover_time(
                    cur,
                    newest_time.isoformat()
                )

    print(
        f"Upserted {len(events)} takeover events",
        flush=True,
    )

if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as exc:
            print(f"Worker error: {exc}", flush=True)

        time.sleep(60)
