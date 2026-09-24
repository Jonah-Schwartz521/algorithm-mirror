"""Algorithm Mirror V3 classifier.

Changes vs V2 (driven by gold-set diagnostics):
- One item per call (batching caused ~half the false 'gaming' labels).
- Topic and tone are separate calls.
- Topic/tone are Literal enums in the JSON schema, so the model can
  only return allowed values (V2 returned 'humor' and 'safety').
- Strict gaming definition with explicit exclusions.
- Short few-shot block of boundary cases (none copied from the gold set).
- No self-reported confidence.

Usage (from server/):
    python label_v3.py --gold     # only the 60 gold items (do this first)
    python label_v3.py            # everything without a V3 label
"""

import sys
import time
from typing import Literal

import ollama
import psycopg
from pydantic import BaseModel

import os
DB_URL = os.environ.get("DATABASE_URL", "postgresql://mirror:mirror@localhost/algorithm_mirror")
OLLAMA_HOST = "http://172.17.176.1:11434"  # Windows GPU Ollama, NOT localhost
MODEL = "llama3.1:8b"
MODEL_VERSION = "llama3.1-8b-v3"
MAX_RETRIES = 2

client = ollama.Client(host=OLLAMA_HOST, timeout=180)

Topic = Literal[
    "sports", "politics", "gaming", "technology", "entertainment", "news",
    "health", "science", "finance", "crime", "lifestyle", "education", "other",
]
Tone = Literal["neutral", "positive", "negative", "outrage", "humor"]


class TopicOut(BaseModel):
    topic: Topic


class ToneOut(BaseModel):
    tone: Tone


TOPIC_PROMPT = """You classify social media content by its PRIMARY SUBJECT.
Pick exactly one topic.

sports: athletes, teams, games, training, highlights, combat sports, sports analysis.
politics: elections, politicians, government, legislation, ballot measures, political opinions.
gaming: ONLY actual video games, game studios, consoles/gaming hardware, esports, or video-game communities.
technology: software, AI, programming, computers, websites, apps, internet services, tech companies, IT certifications.
entertainment: movies, TV, music, DJ sets, comedy, jokes, celebrities, internet culture, storytelling/commentary channels.
news: current events and disasters that fit no more specific topic.
health: medicine, drugs, injuries, bodies, diseases, doctors, nutrition.
science: biology, chemistry, physics, space, paleontology, natural sciences.
finance: money, investing, insurance, taxes as personal money, jobs/careers as income.
crime: crimes, police, shootings, court cases, true crime, unsolved mysteries.
lifestyle: everyday life, hobbies, fitness routines, cannabis/drinking culture, relationships, travel, food.
education: history lessons, explainers, tutorials, academic subjects.
other: only if nothing above fits (e.g. a scenery livestream).

GAMING RULES (important):
- Words like "game", "game-changing", "play", "speedrun", "win", or a video-game name used as a comparison do NOT make something gaming.
- Real-world sports are NEVER gaming.
- Building a game as a coding/AI demo is technology.
- If you are not sure it is about a video game, it is NOT gaming.

Examples:
Title: "This app is a total game changer for my budget" -> finance
Title: "Real life Mario Kart: police chase through downtown" (channel: dashcam news) -> crime
Title: "Speedrunning IKEA furniture assembly" -> entertainment
Title: "Elden Ring DLC boss tier list" -> gaming
Title: "I asked 3 AI models to code Tetris" -> technology
Title: "Perfect your curveball grip" -> sports
Title: "Anyone else sleep better after a run?" (subreddit: r/running) -> lifestyle
Title: "Weird lump on my wrist, what is it?" (subreddit: r/whatisit) -> health

Use the subreddit or channel as a strong hint about the subject.
"""

TONE_PROMPT = """Pick the tone of this social media content.

neutral: informational or factual.
positive: celebratory, exciting, encouraging.
negative: sad, critical, disturbing, worrying.
outrage: primarily angry or morally indignant.
humor: primarily meant to be funny or absurd.

Outrage is rare: only use it when the title itself is angry or accusatory. Disturbing or dramatic subjects are negative, not outrage. If unsure, use neutral.
"""


def describe(platform, channel, title):
    source = channel or "(none)"
    label = "Subreddit" if platform == "reddit" else "Channel"
    return f"Platform: {platform}\n{label}: {source}\nTitle: {(title or '')[:400]}"


def ask(system, content, schema):
    last = None
    for attempt in range(MAX_RETRIES):
        try:
            r = client.chat(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": content},
                ],
                format=schema.model_json_schema(),
                options={"temperature": 0},
            )
            return schema.model_validate_json(r["message"]["content"])
        except Exception as e:
            last = e
            time.sleep(1)
    raise last


def fetch(cur, gold_only):
    gold_filter = "AND i.item_id IN (SELECT item_id FROM gold_labels)" if gold_only else ""
    cur.execute(
        f"""
        SELECT i.item_id, i.platform, i.channel, i.title
        FROM items i
        WHERE i.title IS NOT NULL
          {gold_filter}
          AND NOT EXISTS (
              SELECT 1 FROM item_labels_comparison c
              WHERE c.item_id = i.item_id AND c.model_version = %s)
        ORDER BY i.item_id
        """,
        (MODEL_VERSION,),
    )
    return cur.fetchall()


def main():
    gold_only = "--gold" in sys.argv
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            rows = fetch(cur, gold_only)
        print(f"{MODEL_VERSION}: {len(rows)} items{' (gold only)' if gold_only else ''}\n")

        done = failed = 0
        start = time.time()
        for item_id, platform, channel, title in rows:
            text = describe(platform, channel, title)
            try:
                topic = ask(TOPIC_PROMPT, text, TopicOut).topic
                tone = ask(TONE_PROMPT, text, ToneOut).tone
            except Exception as e:
                failed += 1
                print(f"FAILED {item_id}: {e}")
                continue

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO item_labels_comparison
                        (item_id, topic, tone, confidence, model_version)
                    VALUES (%s, %s, %s, 0, %s)
                    ON CONFLICT (item_id, model_version) DO NOTHING
                    """,
                    (item_id, topic, tone, MODEL_VERSION),
                )
            conn.commit()
            done += 1
            print(f"{done:>3}  {topic:<14}{tone:<10}{(title or '')[:55]}")

        print(f"\nDone: {done} labeled, {failed} failed, {time.time() - start:.0f}s")


if __name__ == "__main__":
    main()