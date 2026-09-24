"""Parse TikTok and Instagram data exports into Algorithm Mirror rows.

Participants download their data (JSON) from the app and upload it here.
The raw file is read in memory and never stored; only the parsed rows are saved.

Every parser returns a list of Row objects in the same shape the extension sends,
so the database, labeler, and dashboard need nothing new.

Export layouts change over time. These parsers search the JSON for the shapes
we expect instead of relying on exact paths. VERIFY against a real export and
adjust the KEY HINTS below if a list is missed.
"""

import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class Row:
    platform: str
    item_id: str
    title: str | None      # caption/text if the export has it (TikTok: filled later by enrich_tiktok.py)
    channel: str | None    # creator / account
    entered_at: datetime   # real timestamp from the export
    evidence: str          # "impression" (shown/watched) or "engagement" (liked/saved)
    media_type: str = "video"
    dwell_ms: int = 0      # TikTok: estimated from the gap to the next video, capped at 60s


# ---------------------------------------------------------------- file reading

def load_json_files(filename: str, data: bytes) -> dict[str, object]:
    """Return {path: parsed_json} for a .zip export or a single .json file."""
    out = {}
    if filename.lower().endswith(".zip") or data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                if name.lower().endswith(".json"):
                    try:
                        out[name] = json.loads(z.read(name).decode("utf-8", "replace"))
                    except json.JSONDecodeError:
                        pass
    else:
        out[filename] = json.loads(data.decode("utf-8", "replace"))
    return out


def walk(obj, path=()):
    """Yield (path_of_keys, value) for every dict/list node."""
    yield path, obj
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, path + (str(k),))
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v, path)


def parse_time(v) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
        t = float(v)
        if t > 1e12:            # milliseconds
            t /= 1000
        return datetime.fromtimestamp(t, tz=timezone.utc)
    if isinstance(v, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                return datetime.strptime(v.strip(), fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
    return None


# ---------------------------------------------------------------- detection

def detect_platform(files: dict[str, object]) -> str | None:
    names = " ".join(files).lower()
    blob = " ".join(files).lower() + " " + " ".join(
        json.dumps(v)[:4000].lower() for v in list(files.values())[:5])
    if "tiktok" in blob or "video browsing history" in blob or ("watch history" in blob and "videolist" in blob):
        return "tiktok"
    if "instagram" in names or "string_map_data" in blob or "impressions_history" in blob or "likes_media_likes" in blob:
        return "instagram"
    return None


# ---------------------------------------------------------------- TikTok
# Known layout (2024-2026): user_data*.json ->
#   "Your Activity" / "Activity" -> "Watch History" | "Video Browsing History" -> "VideoList": [{"Date", "Link"}]
#                               -> "Like List" -> "ItemFavoriteList": [{"date"/"Date", "link"/"Link"}]
# Watch history = every video the For You feed played, so it counts as an impression.

TIKTOK_IMPRESSION_HINTS = ("watch history", "video browsing history", "browsing history")
TIKTOK_ENGAGEMENT_HINTS = ("like list", "favorite", "liked")
TIKTOK_ID = re.compile(r"/video/(\d{8,})")


def parse_tiktok(files: dict[str, object]) -> list[Row]:
    rows: list[Row] = []
    for _, root in files.items():
        for path, node in walk(root):
            if not isinstance(node, list) or not node or not isinstance(node[0], dict):
                continue
            where = " / ".join(path).lower()
            if any(h in where for h in TIKTOK_IMPRESSION_HINTS):
                evidence = "impression"
            elif any(h in where for h in TIKTOK_ENGAGEMENT_HINTS):
                evidence = "engagement"
            else:
                continue
            for e in node:
                if not isinstance(e, dict):
                    continue
                low = {k.lower(): v for k, v in e.items()}
                link, when = low.get("link") or low.get("videolink"), parse_time(low.get("date"))
                m = TIKTOK_ID.search(str(link or ""))
                if not m or not when:
                    continue
                rows.append(Row("tiktok", m.group(1), None, None, when, evidence))
    rows = dedupe(rows)
    # Time on screen ~= time until the next video started (swipe), capped like the extension.
    watched = sorted((r for r in rows if r.evidence == "impression"), key=lambda r: r.entered_at)
    for a, b in zip(watched, watched[1:]):
        a.dwell_ms = int(min((b.entered_at - a.entered_at).total_seconds(), 60) * 1000)
    return rows


# ---------------------------------------------------------------- Instagram
# Known layout (Meta "Download your information", JSON):
#   ads_information/ads_and_topics/posts_viewed.json  -> impressions_history_posts_seen:  [{string_map_data: {Author, Time}}]
#   ads_information/ads_and_topics/videos_watched.json -> impressions_history_videos_watched: [...]
#   your_instagram_activity/likes/liked_posts.json    -> likes_media_likes: [{title: author, string_list_data: [{href, timestamp}]}]
#   your_instagram_activity/saved/saved_posts.json    -> saved_saved_media: [{title, string_map_data: {"Saved on": {href, timestamp}}}]
# "Viewed" entries often have only the account + time (no post link or caption).

IG_POST = re.compile(r"instagram\.com/(?:[\w.]+/)?(?:p|reel|tv)/([\w-]+)")


def _smd_value(smd: dict, *names):
    for n in names:
        for k, v in smd.items():
            if k.lower() == n.lower() and isinstance(v, dict):
                return v
    return {}


def parse_instagram(files: dict[str, object]) -> list[Row]:
    rows: list[Row] = []
    for fname, root in files.items():
        for path, node in walk(root):
            if not isinstance(node, list) or not node or not isinstance(node[0], dict):
                continue
            where = (fname + " / " + " / ".join(path)).lower()

            # Viewed posts / watched videos -> impressions (account + time only)
            if "posts_seen" in where or "posts_viewed" in where or "videos_watched" in where:
                media = "video" if "video" in where else "post"
                for e in node:
                    smd = e.get("string_map_data", {}) if isinstance(e, dict) else {}
                    author = _smd_value(smd, "Author", "Username").get("value")
                    when = parse_time(_smd_value(smd, "Time", "Timestamp").get("timestamp"))
                    if not author or not when:
                        continue
                    # No post id in these files: one row per (account, time) view.
                    item_id = f"ig:{author}:{int(when.timestamp())}"
                    rows.append(Row("instagram", item_id, f"Instagram {media} from @{author}", author, when,
                                    "impression", media))

            # Liked / saved posts -> engagement (these do carry a post link)
            elif "likes_media_likes" in where or "liked_posts" in where or "saved" in where:
                for e in node:
                    if not isinstance(e, dict):
                        continue
                    author = e.get("title") or None
                    entries = e.get("string_list_data") or list((e.get("string_map_data") or {}).values())
                    for d in entries:
                        if not isinstance(d, dict):
                            continue
                        m = IG_POST.search(str(d.get("href", "")))
                        when = parse_time(d.get("timestamp"))
                        if not m or not when:
                            continue
                        title = f"Instagram post from @{author}" if author else None
                        rows.append(Row("instagram", f"ig:{m.group(1)}", title, author, when, "engagement", "post"))
    return dedupe(rows)


# ---------------------------------------------------------------- shared

def dedupe(rows: list[Row]) -> list[Row]:
    seen, out = set(), []
    for r in rows:
        key = (r.item_id, r.entered_at, r.evidence)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


PARSERS = {"tiktok": parse_tiktok, "instagram": parse_instagram}


def parse_export(filename: str, data: bytes) -> tuple[str | None, list[Row]]:
    files = load_json_files(filename, data)
    platform = detect_platform(files)
    if not platform:
        return None, []
    rows = PARSERS[platform](files)
    # Only keep recent history; the study doesn't need years of old videos.
    import os
    from datetime import timedelta
    days = int(os.environ.get("EXPORT_DAYS", "60"))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return platform, [r for r in rows if r.entered_at and r.entered_at >= cutoff]


def save_rows(cur, token: str, rows: list[Row]) -> dict:
    """Insert parsed rows. Re-uploading the same export adds nothing new."""
    added = {"impression": 0, "engagement": 0}
    for i, r in enumerate(rows):
        cur.execute(
            """
            INSERT INTO items (item_id, platform, media_type, title, channel, channel_handle, duration, is_ad)
            VALUES (%s, %s, %s, %s, %s, %s, NULL, false)
            ON CONFLICT (item_id) DO NOTHING
            """,
            (r.item_id, r.platform, r.media_type, r.title, r.channel,
             f"/@{r.channel}" if r.channel else None),
        )
        cur.execute(
            """
            INSERT INTO impressions (user_token, item_id, position, entered_at, dwell_ms, source, evidence)
            VALUES (%s, %s, %s, %s, %s, 'export', %s)
            ON CONFLICT (user_token, item_id, entered_at) DO NOTHING
            """,
            (token, r.item_id, i, r.entered_at, r.dwell_ms, r.evidence),
        )
        added[r.evidence] += cur.rowcount
    return added