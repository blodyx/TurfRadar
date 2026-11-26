from datetime import datetime
from typing import Callable

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field


MAX_IMPORT_ROWS = 3500


class TurfaImportRow(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=80,
    )

    takes: int = Field(
        gt=0,
        le=1_000_000,
    )

    firstTake: datetime | None = None


class TurfaImportRequest(BaseModel):
    rows: list[TurfaImportRow]


def _normalize_name(name: str) -> str:
    return " ".join(
        name.strip().split()
    ).casefold()


def register_turfa_import_routes(
    app,
    get_connection: Callable,
    get_current_user: Callable,
):
    @app.get("/api/import/turfa/status")
    def turfa_import_status(
        request: Request,
    ):
        current_user = get_current_user(
            request
        )

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        COUNT(*) AS imported_players,

                        COALESCE(
                            SUM(take_count),
                            0
                        ) AS imported_takes,

                        COUNT(*) FILTER (
                            WHERE opponent_turf_id
                            IS NOT NULL
                        ) AS matched_ids,

                        MAX(imported_at)
                            AS last_imported_at

                    FROM turfa_taken_players

                    WHERE user_id = %s
                    """,
                    (
                        current_user[
                            "user_id"
                        ],
                    ),
                )

                row = cur.fetchone()

        return {
            "importedPlayers":
                row["imported_players"],

            "importedTakes":
                row["imported_takes"],

            "matchedIds":
                row["matched_ids"],

            "lastImportedAt":
                row["last_imported_at"],
        }


    @app.post("/api/import/turfa")
    def import_turfa_data(
        payload: TurfaImportRequest,
        request: Request,
    ):
        current_user = get_current_user(
            request
        )

        if not payload.rows:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Ingen Turfa-data "
                    "att importera"
                ),
            )

        if len(payload.rows) > MAX_IMPORT_ROWS:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Importen får innehålla "
                    f"högst {MAX_IMPORT_ROWS} "
                    "turfare"
                ),
            )

        deduplicated = {}

        for row in payload.rows:
            clean_name = " ".join(
                row.name.strip().split()
            )

            key = _normalize_name(
                clean_name
            )

            current = deduplicated.get(
                key
            )

            if (
                current is None
                or row.takes > current.takes
            ):
                deduplicated[key] = (
                    row.model_copy(
                        update={
                            "name":
                                clean_name
                        }
                    )
                )

        rows = list(
            deduplicated.values()
        )

        with get_connection() as conn:
            with conn.cursor() as cur:
                for row in rows:
                    normalized_name = (
                        _normalize_name(
                            row.name
                        )
                    )

                    cur.execute(
                        """
                        INSERT INTO
                            turfa_taken_players (
                                user_id,
                                opponent_name,
                                opponent_name_normalized,
                                take_count,
                                first_take_at,
                                imported_at
                            )
                        VALUES (
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            NOW()
                        )

                        ON CONFLICT (
                            user_id,
                            opponent_name_normalized
                        )

                        DO UPDATE SET
                            opponent_name =
                                EXCLUDED.opponent_name,

                            take_count =
                                EXCLUDED.take_count,

                            first_take_at =
                                EXCLUDED.first_take_at,

                            imported_at =
                                NOW()
                        """,
                        (
                            current_user[
                                "user_id"
                            ],

                            row.name,
                            normalized_name,
                            row.takes,
                            row.firstTake,
                        ),
                    )

        return {
            "imported": len(rows),
            "submitted": len(rows),
            "unresolvedCount": 0,
            "unresolved": [],
        }
