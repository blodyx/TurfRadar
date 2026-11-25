import json
import os

import psycopg


def get_connection():
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


UPSERT_SQL = """
INSERT INTO zones (
    id,
    name,
    latitude,
    longitude,
    location,
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
    NOW()
)
ON CONFLICT (id)
DO UPDATE SET
    name = EXCLUDED.name,
    latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude,
    location = EXCLUDED.location,
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
    updated_at = NOW()
"""


def main():
    with open("/data/zones-all.json") as f:
        zones = json.load(f)

    print(f"Loaded {len(zones)} zones", flush=True)

    with get_connection() as conn:
        with conn.cursor() as cur:
            for zone in zones:
                region = zone.get("region") or {}
                area = region.get("area") or {}
                zone_type = zone.get("type") or {}

                cur.execute(
                    UPSERT_SQL,
                    {
                        "id": zone["id"],
                        "name": zone["name"],
                        "latitude": zone["latitude"],
                        "longitude": zone["longitude"],
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
                    },
                )

    print(f"Synced {len(zones)} zones", flush=True)


if __name__ == "__main__":
    main()
