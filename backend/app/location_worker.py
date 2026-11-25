import os
import time

import httpx
import psycopg


LOCATION_URL = "https://api.turfgame.com/v6/users/location"


def get_connection():
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def main():
    response = httpx.get(
        LOCATION_URL,
        timeout=30.0,
    )
    response.raise_for_status()

    locations = response.json()

    by_id = {
        player["id"]: player
        for player in locations
    }

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT turf_user_id
                FROM users
                WHERE active = TRUE
                """
            )

            watched_users = [
                row[0]
                for row in cur.fetchall()
            ]

            updated = 0

            for turf_user_id in watched_users:
                player = by_id.get(turf_user_id)

                if not player:
                    continue

                latitude = player["latitude"]
                longitude = player["longitude"]

                cur.execute(
                    """
                    UPDATE users
                    SET
                        latitude = %s,
                        longitude = %s,
                        location = ST_SetSRID(
                            ST_MakePoint(%s, %s),
                            4326
                        )::geography,
                        position_updated_at = NOW(),
                        updated_at = NOW()
                    WHERE turf_user_id = %s
                    """,
                    (
                        latitude,
                        longitude,
                        longitude,
                        latitude,
                        turf_user_id,
                    ),
                )

                updated += 1

    print(
        f"Location feed: {len(locations)} visible players, "
        f"updated {updated} watched users",
        flush=True,
    )


if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as exc:
            print(
                f"Location worker error: {exc}",
                flush=True,
            )

        time.sleep(30)
