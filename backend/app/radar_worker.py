
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
            )::INTEGER AS distance_m,

            CASE
                WHEN z.current_owner_id IS NULL THEN FALSE
                WHEN z.current_owner_id = u.turf_user_id THEN FALSE
                WHEN utp.opponent_turf_id IS NOT NULL THEN FALSE
                ELSE TRUE
            END AS unique_player

        FROM zones z

        JOIN users u
            ON u.id = %s

        LEFT JOIN user_taken_players utp
            ON utp.user_id = u.id
            AND utp.opponent_turf_id = z.current_owner_id

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

    unique_players = [
        zone
        for zone in zones
        if zone[7]
    ]

    print(
        f"Radar {turf_name}: "
        f"{len(zones)} zones within {radius_m} m, "
        f"{len(unique_players)} unique-player opportunities",
        flush=True,
    )

    for zone in unique_players[:20]:
        (
            zone_id,
            zone_name,
            owner_id,
            owner_name,
            region_id,
            region_name,
            distance_m,
            unique_player,
        ) = zone

        print(
            f"  UNIQUE | "
            f"{distance_m:4d} m | "
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
