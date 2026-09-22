import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel


# --------------------------------------------------
# Configuration
# --------------------------------------------------

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://mirror:mirror@localhost/algorithm_mirror",
)

BASE_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_PATH = BASE_DIR / "dashboard" / "index.html"


# --------------------------------------------------
# FastAPI app
# --------------------------------------------------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.youtube.com",
        "https://www.reddit.com",
        "https://x.com",
        "https://twitter.com",
    ],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


# --------------------------------------------------
# Dashboard
# --------------------------------------------------

@app.get("/")
def dashboard():
    """Serve the Algorithm Mirror dashboard."""
    return FileResponse(DASHBOARD_PATH)


# --------------------------------------------------
# Request models
# --------------------------------------------------

class Item(BaseModel):
    itemId: str
    mediaType: str
    title: str | None = None
    channel: str | None = None
    channelHandle: str | None = None
    duration: str | None = None
    isAd: bool = False
    platform: str


class Event(BaseModel):
    id: int
    itemId: str
    position: int
    enteredAt: int
    dwellMs: int
    source: str
    evidence: str


class Batch(BaseModel):
    userToken: str
    items: list[Item]
    events: list[Event]


# --------------------------------------------------
# Extension sync endpoint
# --------------------------------------------------

@app.post("/sync")
def sync(batch: Batch):
    with psycopg.connect(DB_URL) as conn, conn.cursor() as cur:

        for it in batch.items:
            cur.execute(
                """
                INSERT INTO items (
                    item_id,
                    platform,
                    media_type,
                    title,
                    channel,
                    channel_handle,
                    duration,
                    is_ad
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (item_id) DO NOTHING
                """,
                (
                    it.itemId,
                    it.platform,
                    it.mediaType,
                    it.title,
                    it.channel,
                    it.channelHandle,
                    it.duration,
                    it.isAd,
                ),
            )

        for e in batch.events:
            cur.execute(
                """
                INSERT INTO impressions (
                    user_token,
                    item_id,
                    position,
                    entered_at,
                    dwell_ms,
                    source,
                    evidence
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (
                    user_token,
                    item_id,
                    entered_at
                ) DO NOTHING
                """,
                (
                    batch.userToken,
                    e.itemId,
                    e.position,
                    datetime.fromtimestamp(
                        e.enteredAt / 1000,
                        tz=timezone.utc,
                    ),
                    e.dwellMs,
                    e.source,
                    e.evidence,
                ),
            )

    print(
        f"[sync] user={batch.userToken[:8]} "
        f"items={len(batch.items)} "
        f"events={len(batch.events)}"
    )

    return {
        "accepted": [e.id for e in batch.events]
    }


# --------------------------------------------------
# Database helper
# --------------------------------------------------

def query(sql: str, params: tuple):
    with psycopg.connect(DB_URL) as conn, conn.cursor() as cur:
        cur.execute(sql, params)

        cols = [d.name for d in cur.description]

        return [
            dict(zip(cols, row))
            for row in cur.fetchall()
        ]


# --------------------------------------------------
# Dashboard API
# --------------------------------------------------

@app.get("/users/{token}/summary")
def summary(
    token: str,
    platform: str | None = None,
):
    rows = query(
        """
        SELECT
            COUNT(*) AS impressions,
            MIN(p.entered_at) AS first_seen,
            MAX(p.entered_at) AS last_seen,
            AVG(p.dwell_ms)::int AS avg_dwell_ms,

            SUM(
                CASE
                    WHEN i.media_type = 'short'
                    THEN 1
                    ELSE 0
                END
            )::float / NULLIF(COUNT(*), 0) AS short_share,

            SUM(
                CASE
                    WHEN i.is_ad
                    THEN 1
                    ELSE 0
                END
            )::float / NULLIF(COUNT(*), 0) AS ad_share

        FROM impressions p

        JOIN items i
            ON i.item_id = p.item_id

        WHERE
            p.user_token = %s
            AND p.evidence = 'impression'
            AND (
                %s::text IS NULL
                OR i.platform = %s
            )
        """,
        (
            token,
            platform,
            platform,
        ),
    )

    return rows[0]


@app.get("/users/{token}/channels")
def channels(
    token: str,
    platform: str | None = None,
    limit: int = 10,
):
    return query(
        """
        SELECT
            i.channel,
            i.channel_handle,
            COUNT(*) AS impressions,

            COUNT(*)::float
                / SUM(COUNT(*)) OVER () AS share

        FROM impressions p

        JOIN items i
            ON i.item_id = p.item_id

        WHERE
            p.user_token = %s
            AND p.evidence = 'impression'
            AND i.channel IS NOT NULL
            AND (
                %s::text IS NULL
                OR i.platform = %s
            )

        GROUP BY
            i.channel,
            i.channel_handle

        ORDER BY
            impressions DESC

        LIMIT %s
        """,
        (
            token,
            platform,
            platform,
            limit,
        ),
    )


@app.get("/users/{token}/daily")
def daily(
    token: str,
    platform: str | None = None,
):
    return query(
        """
        SELECT
            DATE(p.entered_at) AS day,
            COUNT(*) AS impressions

        FROM impressions p

        JOIN items i
            ON i.item_id = p.item_id

        WHERE
            p.user_token = %s
            AND p.evidence = 'impression'
            AND (
                %s::text IS NULL
                OR i.platform = %s
            )

        GROUP BY
            day

        ORDER BY
            day
        """,
        (
            token,
            platform,
            platform,
        ),
    )