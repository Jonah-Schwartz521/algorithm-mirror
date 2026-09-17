from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

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
    print(f"[sync] user={batch.userToken} items={len(batch.items)} events={len(batch.events)}")
    for e in batch.events:
        print(f"  {e.itemId} pos={e.position} dwell={e.dwellMs}ms")
    return {"accepted": [e.id for e in batch.events]}