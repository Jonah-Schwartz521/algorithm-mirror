"""Upload page + endpoint for TikTok / Instagram data exports.

Wire into main.py with two lines:
    from uploads import router as upload_router
    app.include_router(upload_router)

Needs:  pip install python-multipart
"""

import os
from pathlib import Path

import psycopg
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from exports import parse_export, save_rows

DB_URL = os.environ.get("DATABASE_URL", "postgresql://mirror:mirror@localhost/algorithm_mirror")
UPLOAD_PAGE = Path(__file__).resolve().parent.parent / "dashboard" / "upload.html"
MAX_BYTES = 500 * 1024 * 1024  # exports with media can be big; JSON-only ones are small

router = APIRouter()


@router.get("/upload")
def upload_page():
    return FileResponse(UPLOAD_PAGE)


EXPORT_PLATFORMS = ("tiktok", "instagram")


@router.get("/users/{token}/uploads")
def list_uploads(token: str):
    """What this person has uploaded, per platform."""
    with psycopg.connect(DB_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.platform,
                   COUNT(*) FILTER (WHERE p.evidence = 'impression') AS viewed,
                   COUNT(*) FILTER (WHERE p.evidence = 'engagement') AS liked,
                   MIN(p.entered_at) AS first_at, MAX(p.entered_at) AS last_at
            FROM impressions p JOIN items i ON i.item_id = p.item_id
            WHERE p.user_token = %s AND p.source = 'export'
            GROUP BY i.platform
            """,
            (token,),
        )
        rows = {r[0]: r for r in cur.fetchall()}
    return [
        {"platform": pl,
         "viewed": rows[pl][1] if pl in rows else 0,
         "liked": rows[pl][2] if pl in rows else 0,
         "first_at": rows[pl][3].isoformat() if pl in rows else None,
         "last_at": rows[pl][4].isoformat() if pl in rows else None}
        for pl in EXPORT_PLATFORMS
    ]


@router.delete("/users/{token}/uploads/{platform}")
def delete_upload(token: str, platform: str):
    """Remove everything this person uploaded for one platform. Extension data is never touched."""
    if platform not in EXPORT_PLATFORMS:
        return JSONResponse({"error": "Unknown platform."}, status_code=400)
    with psycopg.connect(DB_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM impressions p USING items i
            WHERE p.item_id = i.item_id AND p.user_token = %s AND p.source = 'export' AND i.platform = %s
            """,
            (token, platform),
        )
        deleted = cur.rowcount
        # Videos/accounts nobody references anymore: drop them and their labels too.
        orphan = """SELECT item_id FROM items i WHERE i.platform = %s
                    AND NOT EXISTS (SELECT 1 FROM impressions p WHERE p.item_id = i.item_id)"""
        cur.execute(f"DELETE FROM item_labels_comparison WHERE item_id IN ({orphan})", (platform,))
        cur.execute(f"DELETE FROM items WHERE item_id IN ({orphan})", (platform,))
    print(f"[upload] user={token[:8]} deleted {platform} export data ({deleted} rows)")
    return {"platform": platform, "deleted": deleted}


@router.post("/users/{token}/upload")
async def upload_export(token: str, file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > MAX_BYTES:
        return JSONResponse({"error": "That file is too big. Re-download the export as JSON only (no photos/videos)."},
                            status_code=413)
    try:
        platform, rows = parse_export(file.filename or "", data)
    except Exception as e:  # bad zip, not JSON, etc.
        return JSONResponse({"error": f"Couldn't read that file ({type(e).__name__}). Upload the .zip or .json you downloaded."},
                            status_code=400)
    finally:
        del data  # the raw export is never stored

    if not platform:
        return JSONResponse({"error": "This doesn't look like a TikTok or Instagram JSON export."}, status_code=400)
    if not rows:
        return JSONResponse({"platform": platform, "found": 0, "added_impressions": 0, "added_engagement": 0,
                             "note": "The export was recognized but had no watch/view/like history in it."})

    with psycopg.connect(DB_URL) as conn, conn.cursor() as cur:
        added = save_rows(cur, token, rows)

    print(f"[upload] user={token[:8]} platform={platform} found={len(rows)} added={added}")
    return {
        "platform": platform,
        "found": len(rows),
        "added_impressions": added["impression"],
        "added_engagement": added["engagement"],
        "note": "Captions are looked up next, then topics are labeled." if platform == "tiktok"
                else "Topics are labeled in the next labeling run.",
    }