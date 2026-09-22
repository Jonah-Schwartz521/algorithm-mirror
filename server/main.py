import os
from datetime import datetime, timezone

import psycopg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DB_URL = os.environ.get("DATABASE_URL", "postgresql://mirror:mirror@localhost/algorithm_mirror")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://www.youtube.com", "https://www.reddit.com", "https://x.com", "https://twitter.com"],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


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


@app.post("/sync")
def sync(batch: Batch):
    with psycopg.connect(DB_URL) as conn, conn.cursor() as cur:
        for it in batch.items:
            cur.execute(
                """INSERT INTO items (item_id, platform, media_type, title, channel, channel_handle, duration, is_ad)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (item_id) DO NOTHING""",
                (it.itemId, it.platform, it.mediaType, it.title, it.channel, it.channelHandle, it.duration, it.isAd),
            )
        for e in batch.events:
            cur.execute(
                """INSERT INTO impressions (user_token, item_id, position, entered_at, dwell_ms, source, evidence)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (user_token, item_id, entered_at) DO NOTHING""",
                (batch.userToken, e.itemId, e.position,
                 datetime.fromtimestamp(e.enteredAt / 1000, tz=timezone.utc),
                 e.dwellMs, e.source, e.evidence),
            )
    print(f"[sync] user={batch.userToken[:8]} items={len(batch.items)} events={len(batch.events)}")
    return {"accepted": [e.id for e in batch.events]}


def query(sql: str, params: tuple):
    with psycopg.connect(DB_URL) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


@app.get("/users/{token}/summary")
def summary(token: str, platform: str | None = None):
    rows = query(
        """SELECT COUNT(*) AS impressions,
                  MIN(p.entered_at) AS first_seen,
                  MAX(p.entered_at) AS last_seen,
                  AVG(p.dwell_ms)::int AS avg_dwell_ms,
                  SUM(CASE WHEN i.media_type = 'short' THEN 1 ELSE 0 END)::float / NULLIF(COUNT(*), 0) AS short_share,
                  SUM(CASE WHEN i.is_ad THEN 1 ELSE 0 END)::float / NULLIF(COUNT(*), 0) AS ad_share
           FROM impressions p JOIN items i ON i.item_id = p.item_id
           WHERE p.user_token = %s AND p.evidence = 'impression'
             AND (%s::text IS NULL OR i.platform = %s)""",
        (token, platform, platform),
    )
    return rows[0]


@app.get("/users/{token}/channels")
def channels(token: str, platform: str | None = None, limit: int = 10):
    return query(
        """SELECT i.channel, i.channel_handle,
                  COUNT(*) AS impressions,
                  COUNT(*)::float / SUM(COUNT(*)) OVER () AS share
           FROM impressions p JOIN items i ON i.item_id = p.item_id
           WHERE p.user_token = %s AND p.evidence = 'impression' AND i.channel IS NOT NULL
             AND (%s::text IS NULL OR i.platform = %s)
           GROUP BY i.channel, i.channel_handle
           ORDER BY impressions DESC
           LIMIT %s""",
        (token, platform, platform, limit),
    )


@app.get("/users/{token}/daily")
def daily(token: str, platform: str | None = None):
    return query(
        """SELECT DATE(p.entered_at) AS day, COUNT(*) AS impressions
           FROM impressions p JOIN items i ON i.item_id = p.item_id
           WHERE p.user_token = %s AND p.evidence = 'impression'
             AND (%s::text IS NULL OR i.platform = %s)
           GROUP BY day ORDER BY day""",
        (token, platform, platform),
    )


# Serve the dashboard from the same origin so the page can call the API without CORS
app.mount("/dashboard", StaticFiles(directory="../dashboard", html=True), name="dashboard")