import os
from datetime import datetime, timezone

import httpx
import psycopg
import time

ROUNDS_URL = "https://api.turfgame.com/v6/rounds"


def get_connection():
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def get_current_round():
    response = httpx.get(ROUNDS_URL, timeout=30.0)
    response.raise_for_status()

    rounds = response.json()
    now = datetime.now(timezone.utc)

    started = [
        round_
        for round_ in rounds
        if datetime.fromisoformat(round_["start"]) <= now
    ]

    return max(
        started,
        key=lambda round_: datetime.fromisoformat(round_["start"]),
    )

def get_stored_round_start(cur):
    cur.execute(
        "SELECT value FROM system_state WHERE key = 'current_round_start'"
    )
    row = cur.fetchone()
    return row[0] if row else None

def main():
    current_round = get_current_round()
    current_start = current_round["start"]

    with get_connection() as conn:
        with conn.cursor() as cur:
            stored_start = get_stored_round_start(cur)

            if stored_start == current_start:
                print(
                    f'Round unchanged: {current_round["name"]} '
                    f'({current_start})',
                    flush=True,
                )
                return

            print(
                f'Round changed: {stored_start} -> {current_start}',
                flush=True,
            )

            cur.execute(
                """
                UPDATE zones
                SET
                    current_owner_id = NULL,
                    current_owner_name = NULL,
                    date_last_taken = NULL
                """
            )

            cur.execute(
                """
                INSERT INTO system_state (key, value, updated_at)
                VALUES ('current_round_start', %s, NOW())
                ON CONFLICT (key)
                DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_at = NOW()
                """,
                (current_start,),
            )

            cur.execute(
                """
                INSERT INTO system_state (key, value, updated_at)
                VALUES ('last_takeover_time', %s, NOW())
                ON CONFLICT (key)
                DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_at = NOW()
                """,
                (current_start,),
            )

            print(
                f'Round reset completed: {current_round["name"]}',
                flush=True,
            )


if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as exc:
            print(f"Round worker error: {exc}", flush=True)

        time.sleep(600)


