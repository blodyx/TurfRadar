import base64
import os

import httpx
import psycopg
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from cryptography.hazmat.primitives import serialization
from fastapi import FastAPI, HTTPException, Request, Response
from psycopg.rows import dict_row
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="TurfRadar",
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TURF_USERS_URL = "https://api.turfgame.com/v6/users"

VAPID_PUBLIC_KEY_PATH = "/run/secrets/vapid_public.pem"

ALLOWED_RADII = {
    500,
    1000,
    2000,
    5000,
}


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class RadarSettings(BaseModel):
    radiusM: int | None = None
    radarEnabled: bool | None = None


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscription(BaseModel):
    endpoint: str
    keys: PushKeys

class RegisterRequest(BaseModel):
    email: str
    challenge: str


class ClaimRequest(BaseModel):
    challenge: str

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_current_user(request: Request):
    session_token = request.cookies.get("turfradar_session")

    if not session_token:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )

    session_hash = hashlib.sha256(
        session_token.encode()
    ).hexdigest()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    s.id AS session_id,
                    u.id AS user_id,
                    u.turf_user_id,
                    u.turf_name,
                    u.radius_m,
                    u.radar_enabled,
                    a.email
                FROM user_sessions s
                JOIN users u
                    ON u.id = s.user_id
                JOIN user_auth a
                    ON a.user_id = u.id
                WHERE s.session_hash = %s
                  AND s.expires_at > NOW()
                  AND a.email_verified_at IS NOT NULL
                """,
                (session_hash,),
            )

            user = cur.fetchone()

            if user is None:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid or expired session",
                )

            cur.execute(
                """
                UPDATE user_sessions
                SET last_seen_at = NOW()
                WHERE id = %s
                """,
                (user["session_id"],),
            )

    return user

def send_verification_email(email: str, turf_name: str, token: str):
    verify_url = (
        "https://farstad.se/turfradar/"
        f"?verify={token}"
    )

    response = httpx.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
            "Content-Type": "application/json",
        },
        json={
            "from": os.environ["RESEND_FROM"],
            "to": [email],
            "subject": "Verifiera ditt TurfRadar-konto",
            "html": f"""
                <h2>TurfRadar 📡</h2>
                <p>Hej {turf_name}!</p>
                <p>
                    Klicka på länken nedan för att verifiera
                    ditt TurfRadar-konto.
                </p>
                <p>
                    <a href="{verify_url}">
                        Verifiera TurfRadar
                    </a>
                </p>
                <p>Länken är giltig i 15 minuter.</p>
                <p>
                    Om du inte försökte registrera dig på
                    TurfRadar kan du ignorera detta mail.
                </p>
            """,
        },
        timeout=30.0,
    )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail="Verification email could not be sent",
        )

def get_connection():
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        row_factory=dict_row,
    )


def get_vapid_public_key():
    with open(VAPID_PUBLIC_KEY_PATH, "rb") as key_file:
        public_key = serialization.load_pem_public_key(
            key_file.read()
        )

    raw_key = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )

    return (
        base64.urlsafe_b64encode(raw_key)
        .rstrip(b"=")
        .decode("ascii")
    )


def lookup_turf_user_by_email(email: str):
    try:
        response = httpx.post(
            TURF_USERS_URL,
            json=[{"email": email}],
            timeout=30.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="Turf API request failed",
        ) from exc

    users = response.json()

    if not users:
        return None

    return users[0]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "TurfRadar",
    }


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

@app.post("/api/register")
def register(request: RegisterRequest):
    email = request.email.strip().lower()
    challenge = request.challenge.strip()

    if not email:
        raise HTTPException(
            status_code=400,
            detail="Email is required",
        )

    if len(challenge) < 32:
        raise HTTPException(
            status_code=400,
            detail="Invalid login challenge",
        )

    turf_user = lookup_turf_user_by_email(email)

    if turf_user is None:
        raise HTTPException(
            status_code=404,
            detail="No Turf user found for this email",
        )

    turf_user_id = turf_user["id"]
    turf_name = turf_user["name"]

    token = secrets.token_urlsafe(32)

    token_hash = hashlib.sha256(
        token.encode()
    ).hexdigest()

    challenge_hash = hashlib.sha256(
        challenge.encode()
    ).hexdigest()

    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(minutes=15)
    )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (
                    turf_user_id,
                    turf_name
                )
                VALUES (%s, %s)
                ON CONFLICT (turf_user_id)
                DO UPDATE SET
                    turf_name = EXCLUDED.turf_name
                RETURNING id
                """,
                (
                    turf_user_id,
                    turf_name,
                ),
            )

            user = cur.fetchone()
            user_id = user["id"]

            cur.execute(
                """
                INSERT INTO user_auth (
                    user_id,
                    email
                )
                VALUES (%s, %s)
                ON CONFLICT (user_id)
                DO UPDATE SET
                    email = EXCLUDED.email,
                    updated_at = NOW()
                """,
                (
                    user_id,
                    email,
                ),
            )

            cur.execute(
                """
                UPDATE auth_tokens
                SET used_at = NOW()
                WHERE user_id = %s
                  AND used_at IS NULL
                """,
                (user_id,),
            )

            cur.execute(
                """
                INSERT INTO auth_tokens (
                    user_id,
                    token_hash,
                    expires_at
                )
                VALUES (%s, %s, %s)
                """,
                (
                    user_id,
                    token_hash,
                    expires_at,
                ),
            )

            cur.execute(
                """
                INSERT INTO auth_challenges (
                    user_id,
                    challenge_hash,
                    expires_at
                )
                VALUES (%s, %s, %s)
                """,
                (
                    user_id,
                    challenge_hash,
                    expires_at,
                ),
            )

    send_verification_email(
        email=email,
        turf_name=turf_name,
        token=token,
    )

    return {
        "status": "verification_sent",
        "turfUserId": turf_user_id,
        "turfName": turf_name,
    }

@app.get("/api/auth/verify")
def verify_email(token: str):
    token_hash = hashlib.sha256(
        token.encode()
    ).hexdigest()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    t.id,
                    t.user_id,
                    t.expires_at,
                    t.used_at,
                    u.turf_user_id,
                    u.turf_name
                FROM auth_tokens t
                JOIN users u
                    ON u.id = t.user_id
                WHERE t.token_hash = %s
                """,
                (token_hash,),
            )

            auth_token = cur.fetchone()

            if auth_token is None:
                raise HTTPException(
                    status_code=404,
                    detail="Invalid verification token",
                )

            if auth_token["used_at"] is not None:
                raise HTTPException(
                    status_code=410,
                    detail="Verification token has already been used",
                )

            if (
                auth_token["expires_at"]
                <= datetime.now(timezone.utc)
            ):
                raise HTTPException(
                    status_code=410,
                    detail="Verification token has expired",
                )

            cur.execute(
                """
                UPDATE user_auth
                SET
                    email_verified_at = NOW(),
                    updated_at = NOW()
                WHERE user_id = %s
                """,
                (auth_token["user_id"],),
            )

            cur.execute(
                """
                UPDATE auth_tokens
                SET used_at = NOW()
                WHERE id = %s
                """,
                (auth_token["id"],),
            )

            cur.execute(
                """
                UPDATE auth_challenges
                SET verified_at = NOW()
                WHERE user_id = %s
                  AND verified_at IS NULL
                  AND claimed_at IS NULL
                  AND expires_at > NOW()
                """,
                (auth_token["user_id"],),
            )

    return {
        "verified": True,
        "turfUserId": auth_token["turf_user_id"],
        "turfName": auth_token["turf_name"],
    }

@app.post("/api/auth/claim")
def claim_auth(
    request: ClaimRequest,
    response: Response,
):
    challenge = request.challenge.strip()

    if len(challenge) < 32:
        raise HTTPException(
            status_code=400,
            detail="Invalid login challenge",
        )

    challenge_hash = hashlib.sha256(
        challenge.encode()
    ).hexdigest()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    c.id,
                    c.user_id,
                    c.verified_at,
                    c.claimed_at,
                    c.expires_at,
                    u.turf_user_id,
                    u.turf_name
                FROM auth_challenges c
                JOIN users u
                    ON u.id = c.user_id
                WHERE c.challenge_hash = %s
                """,
                (challenge_hash,),
            )

            auth_challenge = cur.fetchone()

            if auth_challenge is None:
                raise HTTPException(
                    status_code=404,
                    detail="Login challenge not found",
                )

            if auth_challenge["claimed_at"] is not None:
                raise HTTPException(
                    status_code=410,
                    detail="Login challenge already claimed",
                )

            if (
                auth_challenge["expires_at"]
                <= datetime.now(timezone.utc)
            ):
                raise HTTPException(
                    status_code=410,
                    detail="Login challenge expired",
                )

            if auth_challenge["verified_at"] is None:
                return {
                    "authenticated": False,
                    "status": "waiting_for_verification",
                }

            session_token = secrets.token_urlsafe(32)

            session_hash = hashlib.sha256(
                session_token.encode()
            ).hexdigest()

            session_expires_at = (
                datetime.now(timezone.utc)
                + timedelta(days=30)
            )

            cur.execute(
                """
                INSERT INTO user_sessions (
                    user_id,
                    session_hash,
                    expires_at
                )
                VALUES (%s, %s, %s)
                """,
                (
                    auth_challenge["user_id"],
                    session_hash,
                    session_expires_at,
                ),
            )

            cur.execute(
                """
                UPDATE auth_challenges
                SET claimed_at = NOW()
                WHERE id = %s
                """,
                (auth_challenge["id"],),
            )

    response.set_cookie(
        key="turfradar_session",
        value=session_token,
        max_age=30 * 24 * 60 * 60,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/turfradar",
    )

    return {
        "authenticated": True,
        "turfUserId": auth_challenge["turf_user_id"],
        "turfName": auth_challenge["turf_name"],
    }


# ---------------------------------------------------------------------------
# Radar
# ---------------------------------------------------------------------------

@app.get("/api/radar")
def radar(request: Request):
    current_user = get_current_user(request)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    turf_user_id,
                    turf_name,
                    radius_m,
                    radar_enabled,
                    latitude,
                    longitude,
                    position_updated_at,
                    EXTRACT(
                        EPOCH FROM (
                            NOW() - position_updated_at
                        )
                    )::INTEGER AS position_age_seconds
                FROM users
                WHERE id = %s
                """,
                (current_user["user_id"],),
            )

            user = cur.fetchone()

            if not user:
                raise HTTPException(
                    status_code=404,
                    detail="Radar user not found",
                )

            if (
                user["latitude"] is None
                or user["longitude"] is None
            ):
                raise HTTPException(
                    status_code=409,
                    detail="No known position",
                )

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
                JOIN users u
                    ON u.id = %s
                WHERE
                    u.location IS NOT NULL
                    AND ST_DWithin(
                        z.location,
                        u.location,
                        u.radius_m
                    )
                ORDER BY distance_m
                """,
                (user["id"],),
            )

            zones = cur.fetchall()

    owned_count = sum(
        1
        for zone in zones
        if zone["current_owner_id"] is not None
    )

    return {
        "user": {
            "turfUserId": user["turf_user_id"],
            "name": user["turf_name"],
            "radiusM": user["radius_m"],
            "radarEnabled": user["radar_enabled"],
            "latitude": user["latitude"],
            "longitude": user["longitude"],
            "positionUpdatedAt": user["position_updated_at"],
            "positionAgeSeconds": user[
                "position_age_seconds"
            ],
        },
        "summary": {
            "zones": len(zones),
            "ownedZones": owned_count,
        },
        "zones": zones[:20],
    }



# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@app.patch("/api/settings")
def update_settings(
    settings: RadarSettings,
    request: Request,
):
    current_user = get_current_user(request)

    if (
        settings.radiusM is None
        and settings.radarEnabled is None
    ):
        raise HTTPException(
            status_code=400,
            detail="No settings supplied",
        )

    if (
        settings.radiusM is not None
        and settings.radiusM not in ALLOWED_RADII
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid radar radius",
        )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET
                    radius_m = COALESCE(
                        %(radius_m)s,
                        radius_m
                    ),
                    radar_enabled = COALESCE(
                        %(radar_enabled)s,
                        radar_enabled
                    ),
                    updated_at = NOW()
                WHERE id = %(user_id)s
                RETURNING
                    radius_m,
                    radar_enabled
                """,
                {
                    "radius_m": settings.radiusM,
                    "radar_enabled": settings.radarEnabled,
                    "user_id": current_user["user_id"],
                },
            )

            row = cur.fetchone()

            if not row:
                raise HTTPException(
                    status_code=404,
                    detail="Radar user not found",
                )

    return {
        "radiusM": row["radius_m"],
        "radarEnabled": row["radar_enabled"],
    }



# ---------------------------------------------------------------------------
# Push
# ---------------------------------------------------------------------------

@app.get("/api/auth/me")
def auth_me(request: Request):
    user = get_current_user(request)

    return {
        "authenticated": True,
        "turfUserId": user["turf_user_id"],
        "turfName": user["turf_name"],
        "email": user["email"],
    }

@app.post("/api/auth/logout")
def logout(
    request: Request,
    response: Response,
):
    session_token = request.cookies.get("turfradar_session")

    if session_token:
        session_hash = hashlib.sha256(
            session_token.encode()
        ).hexdigest()

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM user_sessions
                    WHERE session_hash = %s
                    """,
                    (session_hash,),
                )

    response.delete_cookie(
        key="turfradar_session",
        path="/turfradar",
        secure=True,
        httponly=True,
        samesite="lax",
    )

    return {
        "authenticated": False,
    }



@app.get("/api/push/public-key")
def push_public_key():
    return {
        "publicKey": get_vapid_public_key(),
    }

@app.post("/api/push/subscribe")
def push_subscribe(
    subscription: PushSubscription,
    request: Request,
):
    current_user = get_current_user(request)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO push_subscriptions (
                    user_id,
                    endpoint,
                    p256dh,
                    auth,
                    updated_at
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    NOW()
                )
                ON CONFLICT (endpoint)
                DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    p256dh = EXCLUDED.p256dh,
                    auth = EXCLUDED.auth,
                    updated_at = NOW()
                """,
                (
                    current_user["user_id"],
                    subscription.endpoint,
                    subscription.keys.p256dh,
                    subscription.keys.auth,
                ),
            )

    return {
        "status": "subscribed",
    }

