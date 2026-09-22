"""Label unlabeled items with a topic and tone using a local model.

Text is sent to the local classifier and discarded; only labels persist.
"""

import json
import os

import ollama
import psycopg
from pydantic import BaseModel


DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://mirror:mirror@localhost/algorithm_mirror",
)

MODEL = "gemma3:12b"
MODEL_VERSION = "v2-gemma3-12b-topics"
BATCH = 20

TOPICS = [
    "sports",
    "politics",
    "gaming",
    "tech",
    "entertainment",
    "news",
    "lifestyle",
    "education",
    "other",
]

TONES = [
    "neutral",
    "positive",
    "negative",
    "outrage",
    "humor",
]


# -----------------------------
# Structured Ollama response
# -----------------------------

class Label(BaseModel):
    id: str
    topic: str
    tone: str
    confidence: float


class LabelBatch(BaseModel):
    labels: list[Label]


RESPONSE_SCHEMA = LabelBatch.model_json_schema()


PROMPT = f"""Classify each item below into exactly one topic and one tone.

Allowed topics:
{", ".join(TOPICS)}

Allowed tones:
{", ".join(TONES)}

Return exactly one classification for EVERY item.

Return this exact JSON structure:

{{
  "labels": [
    {{
      "id": "item id",
      "topic": "one allowed topic",
      "tone": "one allowed tone",
      "confidence": 0.0
    }}
  ]
}}

Rules:
- There must be exactly one label for every input item.
- Keep the exact input id.
- Do not invent ids.
- topic must be exactly one of the allowed topics.
- tone must be exactly one of the allowed tones.
- confidence must be a number from 0.0 to 1.0.
- Do not add explanations.
- Do not add markdown.
- Do not return any text outside the JSON object.

Items:
"""


def fetch_unlabeled(cur, limit):
    cur.execute(
        """
        SELECT
            i.item_id,
            i.platform,
            i.channel,
            i.title
        FROM items i
        LEFT JOIN item_labels l
            ON l.item_id = i.item_id
        WHERE l.item_id IS NULL
          AND i.title IS NOT NULL
        LIMIT %s
        """,
        (limit,),
    )

    return cur.fetchall()


def classify(rows):
    items = [
        {
            "id": str(r[0]),
            "platform": r[1],
            "source": r[2],
            "text": (r[3] or "")[:300],
        }
        for r in rows
    ]

    response = ollama.chat(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": PROMPT + json.dumps(items, indent=2),
            }
        ],
        format=RESPONSE_SCHEMA,
        options={
            "temperature": 0,
        },
    )

    text = response["message"]["content"]

    try:
        parsed = LabelBatch.model_validate_json(text)
    except Exception as e:
        raise ValueError(
            f"Ollama returned an invalid structured response:\n{text[:2000]}"
        ) from e

    labels = parsed.labels

    # Make sure Gemma classified every item in the batch.
    if len(labels) != len(rows):
        raise ValueError(
            f"Expected {len(rows)} labels but received {len(labels)}"
        )

    expected_ids = [str(row[0]) for row in rows]
    returned_ids = [label.id for label in labels]

    # Make sure there are no missing, duplicated, or invented IDs.
    if set(returned_ids) != set(expected_ids):
        raise ValueError(
            "Returned IDs do not match the requested batch.\n"
            f"Expected: {expected_ids}\n"
            f"Returned: {returned_ids}"
        )

    if len(set(returned_ids)) != len(returned_ids):
        raise ValueError("Ollama returned duplicate item IDs")

    return labels


def main():
    total = 0

    with psycopg.connect(DB_URL) as conn, conn.cursor() as cur:
        while True:
            rows = fetch_unlabeled(cur, BATCH)

            if not rows:
                break

            print(
                f"classifying {len(rows)} items with {MODEL}..."
            )

            try:
                labels = classify(rows)
            except Exception as e:
                print(f"batch failed, stopping: {e}")
                break

            inserted = 0

            for lab in labels:
                topic = (
                    lab.topic
                    if lab.topic in TOPICS
                    else "other"
                )

                tone = (
                    lab.tone
                    if lab.tone in TONES
                    else "neutral"
                )

                confidence = max(
                    0.0,
                    min(1.0, float(lab.confidence)),
                )

                cur.execute(
                    """
                    INSERT INTO item_labels
                        (item_id, topic, tone, confidence, model_version)
                    VALUES
                        (%s, %s, %s, %s, %s)
                    ON CONFLICT (item_id) DO NOTHING
                    """,
                    (
                        lab.id,
                        topic,
                        tone,
                        confidence,
                        MODEL_VERSION,
                    ),
                )

                inserted += 1

            conn.commit()

            total += inserted

            print(
                f"processed {len(rows)} items, "
                f"inserted {inserted} labels, "
                f"total labeled: {total}"
            )

    print("done")


if __name__ == "__main__":
    main()