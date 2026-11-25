import os

import psycopg
from fastapi import FastAPI, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel


app = FastAPI(
    title="TurfRadar",
    version="0.1.0",
)


ALLOWED_RADII = {
    500,
    1000,
    2000,
    5000,
}


class RadarSettings(BaseModel):
    radiusM: int | None = None
    radarEnabled: bool | None = None


def get_connection():
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        row_factory=dict_row,
    )


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "TurfRadar",
    }


@app.get("/api/radar")
def radar(turf_user_id: int = 28449):
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
                WHERE turf_user_id = %s
                """,
                (turf_user_id,),
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
            "positionUpdatedAt": user[
                "position_updated_at"
            ],
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


@app.patch("/api/settings")
def update_settings(
    settings: RadarSettings,
    turf_user_id: int = 28449,
):
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
                WHERE turf_user_id = %(turf_user_id)s
                RETURNING
                    radius_m,
                    radar_enabled
                """,
                {
                    "radius_m": settings.radiusM,
                    "radar_enabled": settings.radarEnabled,
                    "turf_user_id": turf_user_id,
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
