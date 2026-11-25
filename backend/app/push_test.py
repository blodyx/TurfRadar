import json
import os

import psycopg
from psycopg.rows import dict_row
from pywebpush import webpush


VAPID_PRIVATE_KEY = (
    "/run/secrets/vapid_private.pem"
)


def get_connection():
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        row_factory=dict_row,
    )


def main():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    ps.endpoint,
                    ps.p256dh,
                    ps.auth
                FROM push_subscriptions ps
                JOIN users u
                    ON u.id = ps.user_id
                WHERE u.turf_user_id = 28449
                ORDER BY ps.updated_at DESC
                LIMIT 1
                """
            )

            subscription = cur.fetchone()

    if not subscription:
        raise RuntimeError(
            "No push subscription found"
        )

    subscription_info = {
        "endpoint": subscription["endpoint"],
        "keys": {
            "p256dh": subscription["p256dh"],
            "auth": subscription["auth"],
        },
    }

    payload = {
        "title": "📡 TurfRadar",
        "body": "Testnotis från radarn.",
        "url": "/turfradar/",
    }

    webpush(
        subscription_info=subscription_info,
        data=json.dumps(payload),
        vapid_private_key=VAPID_PRIVATE_KEY,
        vapid_claims={
            "sub": "mailto:kapten@farstad.se"
        },
    )

    print("Push sent", flush=True)


if __name__ == "__main__":
    main()
