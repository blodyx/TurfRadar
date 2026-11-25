import os

import httpx
import psycopg


USERS_URL = "https://api.turfgame.com/v6/users"


def get_connection():
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def sync_user(cur, turf_user_id):
    response = httpx.post(
        USERS_URL,
        json=[{"id": turf_user_id}],
        timeout=30.0,
    )
    response.raise_for_status()

    users = response.json()

    if not users:
        raise RuntimeError(
            f"Turf user {turf_user_id} not found"
        )

    user = users[0]
    region = user.get("region") or {}

    cur.execute(
        """
        UPDATE users
        SET
            turf_name = %(name)s,
            country = %(country)s,
            region_id = %(region_id)s,
            region_name = %(region_name)s,
            unique_zones_taken = %(unique_zones_taken)s,
            total_takes = %(total_takes)s,
            rank = %(rank)s,
            total_points = %(total_points)s,
            profile_updated_at = NOW(),
            updated_at = NOW()
        WHERE turf_user_id = %(id)s
        """,
        {
            "id": user["id"],
            "name": user["name"],
            "country": user.get("country"),
            "region_id": region.get("id"),
            "region_name": region.get("name"),
            "unique_zones_taken": user.get(
                "uniqueZonesTaken"
            ),
            "total_takes": user.get("taken"),
            "rank": user.get("rank"),
            "total_points": user.get("totalPoints"),
        },
    )

    cur.execute(
        """
        SELECT id
        FROM users
        WHERE turf_user_id = %s
        """,
        (user["id"],),
    )

    row = cur.fetchone()

    if not row:
        raise RuntimeError(
            f"Local TurfRadar user {user['id']} not found"
        )

    local_user_id = row[0]

    # Rebuild medals from the current V6 response.
    # Duplicate medal IDs are meaningful and must be preserved.
    cur.execute(
        """
        DELETE FROM user_medals
        WHERE user_id = %s
        """,
        (local_user_id,),
    )

    medal_counts = {}
    medal_rows = []

    for medal_id in user.get("medals", []):
        occurrence = medal_counts.get(medal_id, 0) + 1
        medal_counts[medal_id] = occurrence

        medal_rows.append(
            (
                local_user_id,
                medal_id,
                occurrence,
            )
        )

    if medal_rows:
        cur.executemany(
            """
            INSERT INTO user_medals (
                user_id,
                medal_id,
                occurrence
            )
            VALUES (%s, %s, %s)
            """,
            medal_rows,
        )

    print(
        f'Synced user {user["name"]} '
        f'({user["id"]}) with '
        f'{len(medal_rows)} medal entries',
        flush=True,
    )


def main():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT turf_user_id
                FROM users
                """
            )

            turf_user_ids = [
                row[0]
                for row in cur.fetchall()
            ]

            for turf_user_id in turf_user_ids:
                sync_user(
                    cur,
                    turf_user_id,
                )


if __name__ == "__main__":
    main()
