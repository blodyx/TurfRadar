import json
import os
import time
from collections import defaultdict
from datetime import timedelta

import psycopg
from pywebpush import WebPushException, webpush


VAPID_PRIVATE_KEY = (
    "/run/secrets/vapid_private.pem"
)

VAPID_SUBJECT = "mailto:kapten@farstad.se"

NOTIFICATION_COOLDOWN = timedelta(
    minutes=30
)


def get_connection():
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def send_push(
    cur,
    user_id,
    owner_name,
    zone_name,
    distance_m,
):
    cur.execute(
        """
        SELECT
            id,
            endpoint,
            p256dh,
            auth
        FROM push_subscriptions
        WHERE user_id = %s
        ORDER BY updated_at DESC
        """,
        (user_id,),
    )

    subscriptions = cur.fetchall()

    if not subscriptions:
        print(
            f"  PUSH skipped: "
            f"no subscription for user {user_id}",
            flush=True,
        )
        return False

    if distance_m >= 1000:
        distance_text = (
            f"{distance_m / 1000:.1f} km"
        )
    else:
        distance_text = f"{distance_m} m"

    payload = {
        "title": "📡 Unikaturfare i närheten",
        "body": (
            f"{owner_name} vid {zone_name}, "
            f"{distance_text} bort."
        ),
        "url": "/turfradar/",
    }

    delivered = False

    for (
        subscription_id,
        endpoint,
        p256dh,
        auth,
    ) in subscriptions:
        subscription_info = {
            "endpoint": endpoint,
            "keys": {
                "p256dh": p256dh,
                "auth": auth,
            },
        }

        try:
            webpush(
                subscription_info=subscription_info,
                data=json.dumps(payload),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={
                    "sub": VAPID_SUBJECT
                },
            )

            delivered = True

            print(
                f"  PUSH sent | "
                f"{owner_name} | "
                f"{zone_name} | "
                f"{distance_text}",
                flush=True,
            )

        except WebPushException as exc:
            status_code = None

            if exc.response is not None:
                status_code = (
                    exc.response.status_code
                )

            print(
                f"  PUSH failed | "
                f"subscription "
                f"{subscription_id} | "
                f"HTTP {status_code} | "
                f"{exc}",
                flush=True,
            )

            # 404/410 means the subscription
            # is no longer usable.
            if status_code in (404, 410):
                cur.execute(
                    """
                    DELETE FROM
                        push_subscriptions
                    WHERE id = %s
                    """,
                    (subscription_id,),
                )

    return delivered


def scan_user(cur, user):
    (
        user_id,
        turf_user_id,
        turf_name,
        radius_m,
    ) = user

    # Learn Turf IDs for imported Turfa history
    # from current owners already known locally.
    cur.execute(
        """
        UPDATE turfa_taken_players ttp
        SET opponent_turf_id =
            matches.owner_id
        FROM (
            SELECT DISTINCT
                LOWER(
                    z.current_owner_name
                ) AS owner_name_normalized,
                z.current_owner_id
                    AS owner_id
            FROM zones z
            WHERE
                z.current_owner_id
                    IS NOT NULL
                AND z.current_owner_name
                    IS NOT NULL
        ) matches
        WHERE
            ttp.user_id = %s
            AND ttp.opponent_turf_id
                IS NULL
            AND
                ttp.opponent_name_normalized =
                matches.owner_name_normalized
        """,
        (user_id,),
    )

    # Get only real unique-player zones.
    cur.execute(
        """
        SELECT
            z.id,
            z.name,
            z.current_owner_id,
            z.current_owner_name,

            ROUND(
                ST_Distance(
                    z.location,
                    u.location
                )
            )::INTEGER AS distance_m

        FROM zones z

        JOIN users u
            ON u.id = %s

        LEFT JOIN user_taken_players utp
            ON utp.user_id = u.id
            AND utp.opponent_turf_id =
                z.current_owner_id

        LEFT JOIN turfa_taken_players ttp
            ON ttp.user_id = u.id
            AND (
                ttp.opponent_turf_id =
                    z.current_owner_id

                OR (
                    ttp.opponent_turf_id
                        IS NULL
                    AND
                    ttp.opponent_name_normalized =
                        LOWER(
                            z.current_owner_name
                        )
                )
            )

        WHERE
            u.location IS NOT NULL

            AND z.current_owner_id
                IS NOT NULL

            AND z.current_owner_id
                <> u.turf_user_id

            AND utp.opponent_turf_id
                IS NULL

            AND ttp.id
                IS NULL

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

    # Group by player.
    #
    # One player owning five nearby zones
    # must produce ONE notification.
    players = defaultdict(list)

    for zone in zones:
        (
            zone_id,
            zone_name,
            owner_id,
            owner_name,
            distance_m,
        ) = zone

        players[owner_id].append(
            {
                "zone_id": zone_id,
                "zone_name": zone_name,
                "owner_name": owner_name,
                "distance_m": distance_m,
            }
        )

    visible_player_ids = set(
        players.keys()
    )

    # Mark players that have disappeared
    # from the current radar as not visible.
    if visible_player_ids:
        cur.execute(
            """
            UPDATE radar_player_state
            SET currently_visible = FALSE
            WHERE
                user_id = %s
                AND currently_visible = TRUE
                AND NOT (
                    opponent_turf_id =
                    ANY(%s)
                )
            """,
            (
                user_id,
                list(visible_player_ids),
            ),
        )

    else:
        cur.execute(
            """
            UPDATE radar_player_state
            SET currently_visible = FALSE
            WHERE
                user_id = %s
                AND currently_visible = TRUE
            """,
            (user_id,),
        )

    notifications_sent = 0

    for (
        opponent_turf_id,
        player_zones,
    ) in players.items():
        # Zones are already sorted by
        # distance from SQL.
        nearest = min(
            player_zones,
            key=lambda zone:
                zone["distance_m"],
        )

        owner_name = (
            nearest["owner_name"]
            or str(opponent_turf_id)
        )

        cur.execute(
            """
            SELECT
                currently_visible,
                notified_at
            FROM radar_player_state
            WHERE
                user_id = %s
                AND opponent_turf_id = %s
            """,
            (
                user_id,
                opponent_turf_id,
            ),
        )

        state = cur.fetchone()

        was_visible = (
            state is not None
            and state[0]
        )

        notified_at = (
            state[1]
            if state
            else None
        )

        cur.execute(
            """
            INSERT INTO radar_player_state (
                user_id,
                opponent_turf_id,
                opponent_name,
                currently_visible,
                first_seen_at,
                last_seen_at
            )
            VALUES (
                %s,
                %s,
                %s,
                TRUE,
                NOW(),
                NOW()
            )

            ON CONFLICT (
                user_id,
                opponent_turf_id
            )

            DO UPDATE SET
                opponent_name =
                    EXCLUDED.opponent_name,
                currently_visible = TRUE,
                last_seen_at = NOW()
            """,
            (
                user_id,
                opponent_turf_id,
                owner_name,
            ),
        )

        # Already on the radar during
        # the previous scan.
        if was_visible:
            continue

        # Even after disappearing/reappearing,
        # never notify more often than once
        # per 30 minutes for the same player.
        if notified_at is not None:
            cur.execute(
                """
                SELECT
                    NOW() - %s
                        >= INTERVAL '30 minutes'
                """,
                (notified_at,),
            )

            cooldown_finished = (
                cur.fetchone()[0]
            )

            if not cooldown_finished:
                print(
                    f"  PUSH cooldown | "
                    f"{owner_name}",
                    flush=True,
                )
                continue

        delivered = send_push(
            cur=cur,
            user_id=user_id,
            owner_name=owner_name,
            zone_name=nearest[
                "zone_name"
            ],
            distance_m=nearest[
                "distance_m"
            ],
        )

        if delivered:
            cur.execute(
                """
                UPDATE radar_player_state
                SET notified_at = NOW()
                WHERE
                    user_id = %s
                    AND opponent_turf_id = %s
                """,
                (
                    user_id,
                    opponent_turf_id,
                ),
            )

            notifications_sent += 1

    print(
        f"Radar {turf_name}: "
        f"{len(zones)} unique-player zones, "
        f"{len(players)} unique players, "
        f"{notifications_sent} notifications",
        flush=True,
    )

    for (
        opponent_turf_id,
        player_zones,
    ) in players.items():
        nearest = min(
            player_zones,
            key=lambda zone:
                zone["distance_m"],
        )

        print(
            f"  UNIQUE | "
            f"{nearest['distance_m']:4d} m | "
            f"{nearest['zone_name']} | "
            f"{nearest['owner_name']} "
            f"({opponent_turf_id}) | "
            f"{len(player_zones)} zones",
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
                scan_user(
                    cur,
                    user,
                )


if __name__ == "__main__":
    while True:
        try:
            main()

        except Exception as exc:
            print(
                f"Radar worker error: {exc}",
                flushh=True,
            )

        time.sleep(30)
