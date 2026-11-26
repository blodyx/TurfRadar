import json
import os
import time
from collections import defaultdict

import psycopg
from pywebpush import WebPushException, webpush

VAPID_PRIVATE_KEY = "/run/secrets/vapid_private.pem"
VAPID_SUBJECT = "mailto:kapten@farstad.se"
FTT_PUSH_TEST_TURF_USER_ID = 28449


def get_connection():
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def _subscriptions(cur, user_id):
    cur.execute(
        """
        SELECT id, endpoint, p256dh, auth
        FROM push_subscriptions
        WHERE user_id = %s
        ORDER BY updated_at DESC
        """,
        (user_id,),
    )
    return cur.fetchall()


def send_payload(cur, user_id, payload, log_prefix):
    subscriptions = _subscriptions(cur, user_id)
    if not subscriptions:
        print(f"  {log_prefix} skipped: no subscription for user {user_id}", flush=True)
        return False

    delivered = False
    for subscription_id, endpoint, p256dh, auth in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": endpoint,
                    "keys": {"p256dh": p256dh, "auth": auth},
                },
                data=json.dumps(payload),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_SUBJECT},
            )
            delivered = True
        except WebPushException as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            print(
                f"  {log_prefix} failed | subscription {subscription_id} | HTTP {status_code} | {exc}",
                flush=True,
            )
            if status_code in (404, 410):
                cur.execute("DELETE FROM push_subscriptions WHERE id = %s", (subscription_id,))

    return delivered


def distance_text(distance_m):
    return f"{distance_m / 1000:.1f} km" if distance_m >= 1000 else f"{distance_m} m"


def send_unique_batch(cur, user_id, new_players):
    nearest = min(new_players, key=lambda item: item["distance_m"])
    if len(new_players) == 1:
        title = "📡 Unik turfare i närheten"
        body = (
            f"{nearest['owner_name']} vid {nearest['zone_name']}, "
            f"{distance_text(nearest['distance_m'])} bort."
        )
    else:
        title = f"📡 {len(new_players)} unika turfare i närheten"
        body = (
            f"Närmast: {nearest['owner_name']} vid {nearest['zone_name']}, "
            f"{distance_text(nearest['distance_m'])} bort."
        )

    delivered = send_payload(
        cur,
        user_id,
        {"title": title, "body": body, "url": "/turfradar/"},
        "PUSH",
    )
    if delivered:
        print(f"  PUSH sent | {len(new_players)} unique players | nearest {nearest['owner_name']}", flush=True)
    return delivered


def send_ftt_batch(cur, user_id, new_ftt):
    nearest = min(new_ftt, key=lambda item: item["distance_m"])
    if len(new_ftt) == 1:
        title = "🏁 FTT i närheten"
        suffix = f" · {nearest['takeover_points']} TP" if nearest["takeover_points"] is not None else ""
        body = f"{nearest['zone_name']} · {distance_text(nearest['distance_m'])}{suffix}"
    else:
        title = f"🏁 {len(new_ftt)} FTT i närheten"
        body = f"Närmast: {nearest['zone_name']}, {distance_text(nearest['distance_m'])} bort."

    delivered = send_payload(
        cur,
        user_id,
        {"title": title, "body": body, "url": "/turfradar/"},
        "FTT PUSH",
    )
    if delivered:
        print(f"  FTT PUSH sent | {len(new_ftt)} zones | nearest {nearest['zone_name']}", flush=True)
    return delivered


def scan_user(cur, user):
    user_id, turf_user_id, turf_name, radius_m = user

    cur.execute(
        """
        UPDATE turfa_taken_players ttp
        SET opponent_turf_id = matches.owner_id
        FROM (
            SELECT DISTINCT
                LOWER(z.current_owner_name) AS owner_name_normalized,
                z.current_owner_id AS owner_id
            FROM zones z
            WHERE z.current_owner_id IS NOT NULL
              AND z.current_owner_name IS NOT NULL
        ) matches
        WHERE ttp.user_id = %s
          AND ttp.opponent_turf_id IS NULL
          AND ttp.opponent_name_normalized = matches.owner_name_normalized
        """,
        (user_id,),
    )

    cur.execute(
        """
        SELECT
            z.id,
            z.name,
            z.current_owner_id,
            z.current_owner_name,
            ROUND(ST_Distance(z.location, u.location))::INTEGER AS distance_m
        FROM zones z
        JOIN users u ON u.id = %s
        LEFT JOIN user_taken_players utp
            ON utp.user_id = u.id
            AND utp.opponent_turf_id = z.current_owner_id
        LEFT JOIN turfa_taken_players ttp
            ON ttp.user_id = u.id
            AND (
                ttp.opponent_turf_id = z.current_owner_id
                OR (
                    ttp.opponent_turf_id IS NULL
                    AND ttp.opponent_name_normalized = LOWER(z.current_owner_name)
                )
            )
        WHERE u.location IS NOT NULL
          AND z.current_owner_id IS NOT NULL
          AND z.current_owner_id <> u.turf_user_id
          AND utp.opponent_turf_id IS NULL
          AND ttp.id IS NULL
          AND ST_DWithin(z.location, u.location, u.radius_m)
        ORDER BY distance_m
        """,
        (user_id,),
    )
    zones = cur.fetchall()

    players = defaultdict(list)
    for zone_id, zone_name, owner_id, owner_name, distance_m in zones:
        players[owner_id].append({
            "zone_id": zone_id,
            "zone_name": zone_name,
            "owner_name": owner_name,
            "distance_m": distance_m,
        })

    visible_ids = list(players.keys())
    if visible_ids:
        cur.execute(
            """
            UPDATE radar_player_state
            SET currently_visible = FALSE
            WHERE user_id = %s
              AND currently_visible = TRUE
              AND NOT (opponent_turf_id = ANY(%s))
            """,
            (user_id, visible_ids),
        )
    else:
        cur.execute(
            """
            UPDATE radar_player_state
            SET currently_visible = FALSE
            WHERE user_id = %s AND currently_visible = TRUE
            """,
            (user_id,),
        )

    new_players = []
    for opponent_turf_id, player_zones in players.items():
        nearest = min(player_zones, key=lambda z: z["distance_m"])
        owner_name = nearest["owner_name"] or str(opponent_turf_id)
        cur.execute(
            """
            SELECT currently_visible, notified_at
            FROM radar_player_state
            WHERE user_id = %s AND opponent_turf_id = %s
            """,
            (user_id, opponent_turf_id),
        )
        state = cur.fetchone()
        was_visible = bool(state and state[0])
        notified_at = state[1] if state else None

        cur.execute(
            """
            INSERT INTO radar_player_state (
                user_id, opponent_turf_id, opponent_name,
                currently_visible, first_seen_at, last_seen_at
            )
            VALUES (%s, %s, %s, TRUE, NOW(), NOW())
            ON CONFLICT (user_id, opponent_turf_id)
            DO UPDATE SET
                opponent_name = EXCLUDED.opponent_name,
                currently_visible = TRUE,
                last_seen_at = NOW()
            """,
            (user_id, opponent_turf_id, owner_name),
        )

        eligible = not was_visible
        if eligible and notified_at is not None:
            cur.execute("SELECT NOW() - %s >= INTERVAL '30 minutes'", (notified_at,))
            eligible = cur.fetchone()[0]
        if eligible:
            new_players.append({
                "opponent_turf_id": opponent_turf_id,
                "owner_name": owner_name,
                "zone_name": nearest["zone_name"],
                "distance_m": nearest["distance_m"],
            })

    unique_notification_sent = 0
    if new_players and send_unique_batch(cur, user_id, new_players):
        ids = [item["opponent_turf_id"] for item in new_players]
        cur.execute(
            """
            UPDATE radar_player_state
            SET notified_at = NOW()
            WHERE user_id = %s
              AND opponent_turf_id = ANY(%s)
            """,
            (user_id, ids),
        )
        unique_notification_sent = 1

    cur.execute(
        """
        SELECT
            z.id,
            z.name,
            z.takeover_points,
            z.points_per_hour,
            ROUND(ST_Distance(z.location, u.location))::INTEGER AS distance_m
        FROM zones z
        JOIN users u ON u.id = %s
        WHERE z.is_ftt_candidate = TRUE
          AND u.location IS NOT NULL
          AND ST_DWithin(z.location, u.location, u.radius_m)
        ORDER BY distance_m
        """,
        (user_id,),
    )
    ftt_zones = cur.fetchall()

    new_ftt = []
    for zone_id, zone_name, takeover_points, points_per_hour, distance_m in ftt_zones:
        cur.execute(
            """
            SELECT notified_at
            FROM radar_ftt_state
            WHERE user_id = %s AND zone_id = %s
            """,
            (user_id, zone_id),
        )
        state = cur.fetchone()
        cur.execute(
            """
            INSERT INTO radar_ftt_state (user_id, zone_id, first_seen_at, last_seen_at)
            VALUES (%s, %s, NOW(), NOW())
            ON CONFLICT (user_id, zone_id)
            DO UPDATE SET last_seen_at = NOW()
            """,
            (user_id, zone_id),
        )
        if state is None or state[0] is None:
            new_ftt.append({
                "zone_id": zone_id,
                "zone_name": zone_name,
                "takeover_points": takeover_points,
                "points_per_hour": points_per_hour,
                "distance_m": distance_m,
            })

    ftt_notification_sent = 0
    if (
        turf_user_id == FTT_PUSH_TEST_TURF_USER_ID
        and new_ftt
        and send_ftt_batch(cur, user_id, new_ftt)
    ):
        ids = [item["zone_id"] for item in new_ftt]
        cur.execute(
            """
            UPDATE radar_ftt_state
            SET notified_at = NOW()
            WHERE user_id = %s
              AND zone_id = ANY(%s)
            """,
            (user_id, ids),
        )
        ftt_notification_sent = 1

    print(
        f"Radar {turf_name}: {len(zones)} unique-player zones, "
        f"{len(players)} unique players, {len(ftt_zones)} FTT candidates, "
        f"{unique_notification_sent} unique push, {ftt_notification_sent} FTT push",
        flush=True,
    )

    for opponent_turf_id, player_zones in players.items():
        nearest = min(player_zones, key=lambda z: z["distance_m"])
        print(
            f"  UNIQUE | {nearest['distance_m']:4d} m | {nearest['zone_name']} | "
            f"{nearest['owner_name']} ({opponent_turf_id}) | {len(player_zones)} zones",
            flush=True,
        )

    for zone_id, zone_name, takeover_points, points_per_hour, distance_m in ftt_zones:
        print(
            f"  FTT | {distance_m:4d} m | {zone_name} | "
            f"{takeover_points or '-'} TP | {points_per_hour or '-'} PPH | zone {zone_id}",
            flush=True,
        )


def main():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, turf_user_id, turf_name, radius_m
                FROM users
                WHERE radar_enabled = TRUE
                """
            )
            for user in cur.fetchall():
                scan_user(cur, user)


if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as exc:
            print(f"Radar worker error: {exc}", flush=True)
        time.sleep(30)

