import os

import httpx
import psycopg


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


def main():
    response = httpx.get(TAKEOVER_URL, timeout=30.0)
    response.raise_for_status()
    events = response.json()

    print(f"Received {len(events)} takeover events")

    with get_connection() as conn:
        with conn.cursor() as cur:
            for event in events:
                upsert_zone(cur, event)

    print(f"Upserted {len(events)} takeover events")


if __name__ == "__main__":
    main()
