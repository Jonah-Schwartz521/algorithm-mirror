"""Algorithm Mirror V2 classifier.

Uses Llama 3.1 8B through Windows Ollama and stores V2 results
separately from the original V1 results.

Behavior:
- Classifies items in batches.
- Recovers missing IDs individually.
- Repairs obvious topic/tone swaps.
- Falls back to per-item classification if a batch fails.
- Records permanently failed items so they are not retried forever.
- Continues through the entire dataset.
"""

import json
import os
import time

import ollama
import psycopg
from pydantic import BaseModel


# ============================================================
# DATABASE
# ============================================================

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://mirror:mirror@localhost/algorithm_mirror",
)


# ============================================================
# OLLAMA
# ============================================================

# Windows Ollama reachable from WSL.
OLLAMA_HOST = "http://172.17.176.1:11434"

MODEL = "llama3.1:8b"
MODEL_VERSION = "llama3.1-8b-v2"

# Keep this small because your 8B model has occasionally
# produced malformed structured output with larger batches.
BATCH = 5

# Large enough to process the entire current dataset.
MAX_ITEMS = 100000

MAX_RETRIES = 2
RETRY_DELAY = 1

# Maximum time for one HTTP request.
REQUEST_TIMEOUT = 180


# ============================================================
# TAXONOMY
# ============================================================

TOPICS = [
    "sports",
    "politics",
    "gaming",
    "technology",
    "entertainment",
    "news",
    "health",
    "science",
    "finance",
    "crime",
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


# ============================================================
# OLLAMA CLIENT
# ============================================================

client = ollama.Client(
    host=OLLAMA_HOST,
    timeout=REQUEST_TIMEOUT,
)


# ============================================================
# PYDANTIC RESPONSE MODELS
# ============================================================

class Label(BaseModel):
    id: str
    topic: str
    tone: str
    confidence: float


class LabelBatch(BaseModel):
    labels: list[Label]


RESPONSE_SCHEMA = LabelBatch.model_json_schema()


# ============================================================
# PROMPT
# ============================================================

PROMPT = f"""
Classify each item below into exactly one topic and one tone.

============================================================
TOPICS
============================================================

sports:
Professional or amateur sports, teams, athletes, games, scores,
highlights, sports analysis, fantasy sports, and sports culture.

politics:
Political candidates, elections, political parties, governments,
political campaigns, legislation, voting, and political debate.

gaming:
Video games, gaming hardware, game releases, esports, streamers,
and gaming communities.

technology:
Software, artificial intelligence, programming, computers,
electronics, technology companies, and digital products.

entertainment:
Movies, television, music, celebrities, comedy, books, creators,
podcasts, and general entertainment content.

news:
Current events, breaking news, major events, and general news
that do not fit a more specific category.

health:
Medicine, healthcare, diseases, drugs, nutrition, fitness,
medical conditions, and physical or mental health.

science:
Scientific research, biology, chemistry, physics, astronomy,
space, paleontology, geology, and natural sciences.

finance:
Money, investing, banking, personal finance, insurance,
markets, taxes, business finance, and financial products.

crime:
Criminal cases, investigations, policing, arrests, courts,
criminal activity, and true crime.

lifestyle:
Everyday life, relationships, hobbies, travel, food, fashion,
self-improvement, and general lifestyle content.

education:
Teaching, learning, tutorials, academic subjects, courses,
and educational material.

other:
Use only when the content clearly does not fit any category above.

============================================================
CATEGORY PRIORITY RULES
============================================================

Choose the MOST SPECIFIC category.

Examples:

A sports game reported by a news channel -> sports

A medical story reported by a news channel -> health

A scientific discovery reported by a news channel -> science

A crime story reported by a news channel -> crime

A political story reported by a news channel -> politics

A programming tutorial -> technology

A video game review -> gaming

A finance or investing discussion -> finance

Do NOT use "other" when one of the defined categories reasonably
fits the content.

============================================================
ALLOWED TOPICS
============================================================

{", ".join(TOPICS)}

============================================================
TONES
============================================================

neutral:
Informational, factual, descriptive, or emotionally neutral.

positive:
Celebratory, encouraging, exciting, happy, successful, or favorable.

negative:
Sad, critical, disappointing, concerning, disturbing, or unfavorable.

outrage:
Content primarily expressing anger, indignation, shock, or moral outrage.

humor:
Content primarily intended to be funny, comedic, absurd, or playful.

============================================================
OUTPUT
============================================================

Return exactly one classification for EVERY input item.

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

- There must be one valid label for every requested item.
- Keep the exact input ID.
- Do not invent IDs.
- Do not omit IDs.
- Do not duplicate IDs.
- topic must be exactly one allowed topic.
- tone must be exactly one allowed tone.
- confidence must be between 0.0 and 1.0.
- Do not add explanations.
- Do not add markdown.
- Return only the JSON object.

Items:

"""


# ============================================================
# DATABASE SETUP
# ============================================================

def ensure_failure_table(conn):
    """Create a table for permanently failed classifications."""

    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS classification_failures (
                item_id TEXT NOT NULL,
                model_version TEXT NOT NULL,
                error TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (item_id, model_version)
            )
            """
        )

    conn.commit()


# ============================================================
# FETCH WORK
# ============================================================

def fetch_unlabeled(cur, limit):
    """
    Fetch items that do not yet have a V2 label and have not already
    been permanently marked as failed.
    """

    cur.execute(
        """
        SELECT
            i.item_id,
            i.platform,
            i.channel,
            i.title
        FROM items i
        WHERE i.title IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM item_labels_comparison c
              WHERE c.item_id = i.item_id
                AND c.model_version = %s
          )
          AND NOT EXISTS (
              SELECT 1
              FROM classification_failures f
              WHERE f.item_id = i.item_id
                AND f.model_version = %s
          )
        ORDER BY i.item_id
        LIMIT %s
        """,
        (
            MODEL_VERSION,
            MODEL_VERSION,
            limit,
        ),
    )

    return cur.fetchall()


# ============================================================
# BUILD MODEL INPUT
# ============================================================

def build_items(rows):
    return [
        {
            "id": str(row[0]),
            "platform": row[1],
            "source": row[2],
            "text": (row[3] or "")[:300],
        }
        for row in rows
    ]


# ============================================================
# VALIDATE / REPAIR
# ============================================================

def validate_label(label):
    """
    Validate one label and repair an obvious topic/tone swap.

    Example:
        topic = "humor"
        tone = "entertainment"

    becomes:
        topic = "entertainment"
        tone = "humor"
    """

    if label.topic in TONES and label.tone in TOPICS:
        print(
            f"  repairing swapped topic/tone for {label.id}: "
            f"{label.topic} <-> {label.tone}"
        )

        label.topic, label.tone = (
            label.tone,
            label.topic,
        )

    if label.topic not in TOPICS:
        raise ValueError(
            f"Invalid topic '{label.topic}' "
            f"for item {label.id}"
        )

    if label.tone not in TONES:
        raise ValueError(
            f"Invalid tone '{label.tone}' "
            f"for item {label.id}"
        )

    confidence = float(label.confidence)

    if not 0.0 <= confidence <= 1.0:
        raise ValueError(
            f"Invalid confidence '{confidence}' "
            f"for item {label.id}"
        )


# ============================================================
# RAW OLLAMA REQUEST
# ============================================================

def request_labels(rows):
    items = build_items(rows)

    response = client.chat(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": PROMPT + json.dumps(
                    items,
                    indent=2,
                ),
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
            "Invalid structured JSON returned by Ollama:\n"
            f"{text[:3000]}"
        ) from e

    return parsed.labels


# ============================================================
# CLASSIFY SINGLE ITEM
# ============================================================

def classify_single_row(row):
    """
    Classify one item.

    Returns:
        Label on success
        None on permanent failure
    """

    item_id = str(row[0])

    for attempt in range(1, MAX_RETRIES + 1):

        try:
            print(
                f"    individual request "
                f"{attempt}/{MAX_RETRIES}..."
            )

            labels = request_labels([row])

            matching = [
                label
                for label in labels
                if label.id == item_id
            ]

            if len(matching) != 1:
                raise ValueError(
                    f"Expected one label for {item_id}, "
                    f"received IDs: "
                    f"{[label.id for label in labels]}"
                )

            label = matching[0]

            validate_label(label)

            return label

        except Exception as e:

            print(
                f"    individual attempt failed: {e}"
            )

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    print(
        f"    PERMANENT FAILURE: "
        f"could not classify {item_id}"
    )

    return None


# ============================================================
# CLASSIFY BATCH
# ============================================================

def classify_rows(rows):
    """
    Classify a batch.

    If the model omits IDs, recover them individually.
    If the batch is malformed, fall back to individual items.
    """

    expected_ids = [
        str(row[0])
        for row in rows
    ]

    expected_id_set = set(expected_ids)

    last_error = None

    # --------------------------------------------------------
    # Try the normal batch request.
    # --------------------------------------------------------

    for attempt in range(1, MAX_RETRIES + 1):

        try:

            print(
                f"  Ollama batch request "
                f"{attempt}/{MAX_RETRIES}..."
            )

            raw_labels = request_labels(rows)

            # Only keep IDs we actually requested.
            valid_labels = [
                label
                for label in raw_labels
                if label.id in expected_id_set
            ]

            returned_ids = [
                label.id
                for label in valid_labels
            ]

            # Duplicate requested IDs are invalid.
            if len(returned_ids) != len(set(returned_ids)):
                raise ValueError(
                    "Ollama returned duplicate requested IDs."
                )

            # Validate all labels returned.
            for label in valid_labels:
                validate_label(label)

            returned_id_set = set(returned_ids)

            missing_ids = (
                expected_id_set - returned_id_set
            )

            # ------------------------------------------------
            # Entire batch is valid.
            # ------------------------------------------------

            if not missing_ids:

                label_by_id = {
                    label.id: label
                    for label in valid_labels
                }

                return [
                    label_by_id[item_id]
                    for item_id in expected_ids
                ]

            # ------------------------------------------------
            # Some IDs missing.
            # Recover missing ones individually.
            # ------------------------------------------------

            print(
                f"  Model returned "
                f"{len(valid_labels)}/{len(rows)} "
                f"requested labels."
            )

            print(
                f"  Missing IDs: "
                f"{sorted(missing_ids)}"
            )

            recovered = list(valid_labels)

            row_by_id = {
                str(row[0]): row
                for row in rows
            }

            for missing_id in sorted(missing_ids):

                print(
                    f"  Retrying missing item "
                    f"{missing_id} individually..."
                )

                missing_label = classify_single_row(
                    row_by_id[missing_id]
                )

                if missing_label is None:
                    raise ValueError(
                        f"Could not recover missing item "
                        f"{missing_id}"
                    )

                recovered.append(
                    missing_label
                )

            recovered_by_id = {
                label.id: label
                for label in recovered
            }

            if set(recovered_by_id.keys()) != expected_id_set:
                raise ValueError(
                    "Recovered batch still does not contain "
                    "exactly the requested IDs."
                )

            return [
                recovered_by_id[item_id]
                for item_id in expected_ids
            ]

        except Exception as e:

            last_error = e

            print(
                f"  batch attempt "
                f"{attempt}/{MAX_RETRIES} failed: {e}"
            )

            if attempt < MAX_RETRIES:
                print(
                    f"  retrying in "
                    f"{RETRY_DELAY} second(s)..."
                )

                time.sleep(RETRY_DELAY)

    # --------------------------------------------------------
    # Batch still failed.
    #
    # Instead of stopping the whole run, fall back to
    # classifying each item individually.
    # --------------------------------------------------------

    print()
    print(
        "  Batch failed after retries."
    )
    print(
        "  Falling back to individual item classification..."
    )

    individual_results = []

    for row in rows:

        item_id = str(row[0])

        print(
            f"  Individual fallback for {item_id}..."
        )

        label = classify_single_row(row)

        if label is not None:
            individual_results.append(label)

    # If every item succeeded individually, return them.
    if len(individual_results) == len(rows):

        labels_by_id = {
            label.id: label
            for label in individual_results
        }

        return [
            labels_by_id[item_id]
            for item_id in expected_ids
        ]

    # Otherwise return only the successfully classified items.
    print(
        f"  Individual fallback classified "
        f"{len(individual_results)}/{len(rows)} items."
    )

    return individual_results


# ============================================================
# SAVE PERMANENT FAILURE
# ============================================================

def save_failure(cur, item_id, error):
    cur.execute(
        """
        INSERT INTO classification_failures
            (
                item_id,
                model_version,
                error
            )
        VALUES
            (%s, %s, %s)
        ON CONFLICT
            (item_id, model_version)
        DO UPDATE SET
            error = EXCLUDED.error,
            created_at = CURRENT_TIMESTAMP
        """,
        (
            str(item_id),
            MODEL_VERSION,
            str(error)[:2000],
        ),
    )


# ============================================================
# MAIN
# ============================================================

def main():

    total_labeled = 0
    total_failed = 0

    print("=" * 60)
    print("Algorithm Mirror V2 FULL DATASET RUN")
    print(f"Model: {MODEL}")
    print(f"Version: {MODEL_VERSION}")
    print(f"Batch size: {BATCH}")
    print("Processing all remaining V2-unlabeled items")
    print("=" * 60)

    with psycopg.connect(DB_URL) as conn:

        ensure_failure_table(conn)

        while total_labeled + total_failed < MAX_ITEMS:

            with conn.cursor() as cur:

                rows = fetch_unlabeled(
                    cur,
                    BATCH,
                )

            if not rows:

                print()
                print(
                    "No more V2-unlabeled items."
                )

                break

            print()
            print(
                f"classifying {len(rows)} items with "
                f"{MODEL} ({MODEL_VERSION})..."
            )

            try:

                labels = classify_rows(rows)

            except Exception as e:

                # ------------------------------------------------
                # If classify_rows itself fails, record each item
                # as failed so this batch will not loop forever.
                # ------------------------------------------------

                print()
                print(
                    "Batch could not be completed."
                )
                print(
                    f"Error: {e}"
                )

                with conn.cursor() as cur:

                    for row in rows:

                        item_id = str(row[0])

                        save_failure(
                            cur,
                            item_id,
                            str(e),
                        )

                conn.commit()

                total_failed += len(rows)

                print(
                    f"Marked {len(rows)} items as failed "
                    f"and continuing."
                )

                continue

            # ----------------------------------------------------
            # Save successful labels.
            # ----------------------------------------------------

            labeled_ids = set()

            with conn.cursor() as cur:

                for label in labels:

                    topic = (
                        label.topic
                        if label.topic in TOPICS
                        else "other"
                    )

                    tone = (
                        label.tone
                        if label.tone in TONES
                        else "neutral"
                    )

                    confidence = max(
                        0.0,
                        min(
                            1.0,
                            float(label.confidence),
                        ),
                    )

                    cur.execute(
                        """
                        INSERT INTO item_labels_comparison
                            (
                                item_id,
                                topic,
                                tone,
                                confidence,
                                model_version
                            )
                        VALUES
                            (%s, %s, %s, %s, %s)
                        ON CONFLICT
                            (item_id, model_version)
                        DO NOTHING
                        """,
                        (
                            label.id,
                            topic,
                            tone,
                            confidence,
                            MODEL_VERSION,
                        ),
                    )

                    labeled_ids.add(label.id)

                # -----------------------------------------------
                # Any items from this batch that did not receive
                # a label are permanently recorded as failures.
                # -----------------------------------------------

                for row in rows:

                    item_id = str(row[0])

                    if item_id not in labeled_ids:

                        save_failure(
                            cur,
                            item_id,
                            (
                                "Item was not successfully "
                                "classified during batch "
                                "or individual fallback."
                            ),
                        )

                        total_failed += 1

            conn.commit()

            total_labeled += len(labeled_ids)

            print(
                f"processed {len(rows)} items, "
                f"inserted {len(labeled_ids)} labels, "
                f"total V2 labeled: {total_labeled}, "
                f"failed: {total_failed}"
            )

    print()
    print("=" * 60)
    print("FULL V2 RUN COMPLETE")
    print(f"Total labeled: {total_labeled}")
    print(f"Total failed: {total_failed}")
    print("=" * 60)


if __name__ == "__main__":
    main()