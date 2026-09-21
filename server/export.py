"""Dump one user's impressions (joined to items) as JSON for the dashboard team."""
import json
import os
import sys
from datetime import datetime

import psycopg

DB_URL = os.environ.get("DATABASE_URL", "postgresql://mirror:mirror@localhost/algorithm_mirror")

QUERY = """
SELECT p.entered_at, p.dwell_ms, p.position, p.source, p.evidence,
       i.item_id, i.platform, i.media_type, i.title, i.channel, i.channel_handle,
       i.duration, i.is_ad
FROM impressions p
JOIN items i ON i.item_id = p.item_id
WHERE p.user_token = %s
ORDER BY p.entered_at
"""


def export(user_token: str, out_path: str):
    with psycopg.connect(DB_URL) as conn, conn.cursor() as cur:
        cur.execute(QUERY, (user_token,))
        cols = [d.name for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    with open(out_path, "w") as f:
        json.dump(rows, f, indent=2, default=str)
    print(f"wrote {len(rows)} impressions to {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python export.py <user_token> [out_path]")
        sys.exit(1)
    token = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else f"exports/{token[:8]}_{datetime.now():%Y%m%d}.json"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    export(token, out)