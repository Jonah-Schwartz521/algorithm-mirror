"""Fill in captions + creators for TikTok videos that came from an export.

The TikTok export only has video links. This looks each one up with TikTok's
public oEmbed endpoint so label_v3.py has text to label.

Run from server/ after an upload:   python enrich_tiktok.py
Then:                               python label_v3.py
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import psycopg

DB_URL = os.environ.get("DATABASE_URL", "postgresql://mirror:mirror@localhost/algorithm_mirror")
OEMBED = "https://www.tiktok.com/oembed?url="
DELAY_S = 0.4          # be polite; ~150 videos/minute
UNAVAILABLE = "(unavailable)"


def lookup(video_id: str):
    # oEmbed wants a full video URL; the @handle part is not checked, the id is what matters.
    url = OEMBED + urllib.parse.quote(f"https://www.tiktok.com/@_/video/{video_id}", safe="")
    req = urllib.request.Request(url, headers={"User-Agent": "AlgorithmMirror/0.1 (research project)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read())
    return (d.get("title") or "").strip() or None, d.get("author_unique_id") or d.get("author_name")


def main():
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT item_id FROM items
                           WHERE platform = 'tiktok' AND title IS NULL
                             AND COALESCE(channel, '') <> %s""", (UNAVAILABLE,))
            ids = [r[0] for r in cur.fetchall()]
        print(f"{len(ids)} TikTok videos need captions")

        ok = gone = 0
        for i, vid in enumerate(ids, 1):
            try:
                title, author = lookup(vid)
                # Caption can be empty (music-only videos): fall back to the creator so it can still be labeled.
                title = title or (f"TikTok video from @{author}" if author else None)
                with conn.cursor() as cur:
                    cur.execute("UPDATE items SET title = %s, channel = %s, channel_handle = %s WHERE item_id = %s",
                                (title, author, f"/@{author}" if author else None, vid))
                ok += 1
            except urllib.error.HTTPError as e:
                if e.code in (400, 403, 404):  # deleted or private video: don't retry forever
                    with conn.cursor() as cur:
                        cur.execute("UPDATE items SET channel = %s WHERE item_id = %s", (UNAVAILABLE, vid))
                    gone += 1
                else:
                    print(f"  {vid}: HTTP {e.code}, will retry next run")
            except Exception as e:
                print(f"  {vid}: {type(e).__name__}, will retry next run")
            conn.commit()
            if i % 25 == 0:
                print(f"  {i}/{len(ids)}  captions={ok}  unavailable={gone}")
            time.sleep(DELAY_S)

        print(f"Done: {ok} captioned, {gone} unavailable. Next: python label_v3.py")


if __name__ == "__main__":
    main()