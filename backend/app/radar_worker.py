import os
import time

import psycopg


def get_connection():
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def scan_user(cur, user):
    (
        user_id,
        turf_user_id,
        turf_name,
        radius_m,
    ) = user

    cur.execute(
        """
        SELECT
            z.id,
            z.name,
            z.current_owner_id,
            z.current_owner_name,
            z.region_id,
            z.region_name,
            ROUND(
                ST_Distance(
                    z.location,
                    u.location
                )
            )::INTEGER AS distance_m
        FROM zones z
        JOIN users u ON u.id = %s
        WHERE
            u.location IS NOT NULL
            AND ST_DWithin(
                z.location,
                u.location,
                u.radius_m
            )
        ORDER BY distance_m
        """,
        (user_id,),
    )

    zones = cur.fetchall()

    owned_zones = [
        zone
        for zone in zones
        if zone[2] is not None
    ]

    print(
        f"Radar {turf_name}: "
        f"{len(zones)} zones within {radius_m} m, "
        f"{len(owned_zones)} currently owned",
        flush=True,
    )

    for zone in owned_zones[:10]:
        (
            zone_id,
            zone_name,
            owner_id,
            owner_name,
            region_id,
            region_name,
            distance_m,
        ) = zone

        print(
            f"  {distance_m:4d} m | "
            f"{zone_name} | "
            f"{owner_name} ({owner_id})",
            flush=True,
        )


def main():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    turf_user_id,
                    turf_name,
                    radius_m
                FROM users
                WHERE radar_enabled = TRUE
                """
            )

            users = cur.fetchall()

            for user in users:
                scan_user(cur, user)


if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as exc:
            print(
                f"Radar worker error: {exc}",
                flush=True,
            )

        time.sleep(30)
