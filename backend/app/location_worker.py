import os

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
    response = httpx.get(LOCATION_URL, timeout=30.0)
    response.raise_for_status()

    locations = response.json()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT turf_user_id
                FROM users
                WHERE active = TRUE
                """
            )

            watched_ids = {row[0] for row in cur.fetchall()}

            matches = [
                player
                for player in locations
                if player["id"] in watched_ids
            ]

            for player in matches:
                cur.execute(
                    """
                    UPDATE users
                    SET
                        turf_name = %s,
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
                        player["name"],
                        player["latitude"],
                        player["longitude"],
                        player["longitude"],
                        player["latitude"],
                        player["id"],
                    ),
                )

    print(
        f"Location feed: {len(locations)} players, "
        f"{len(matches)} watched users found",
        flush=True,
    )


if __name__ == "__main__":
    main()
