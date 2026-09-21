from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os 
import psycopg
from datetime import datetime, timezone
app = FastAPI()

DB_URL = os.environ.get("DATABASE_URL", "postgresql://mirror:mirror@localhost/algorithm_mirror")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://www.youtube.com"],
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