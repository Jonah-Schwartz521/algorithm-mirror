import psycopg
import label as v2

SQL = """
SELECT i.item_id, i.platform, i.channel, i.title, g.topic AS gold
FROM items i
JOIN item_labels_comparison c
  ON c.item_id = i.item_id AND c.model_version = 'llama3.1-8b-v2'
LEFT JOIN gold_labels g ON g.item_id = i.item_id
WHERE c.topic = 'gaming'
ORDER BY i.item_id
"""

def main():
    with psycopg.connect(v2.DB_URL) as conn, conn.cursor() as cur:
        cur.execute(SQL)
        rows = cur.fetchall()
    print(f"Re-running {len(rows)} V2 'gaming' items individually...\n")
    still_gaming = matches_gold = 0
    for item_id, platform, channel, title, gold in rows:
        try:
            labels = v2.request_labels([(item_id, platform, channel, title)])
            solo = labels[0].topic if labels else "(none)"
        except Exception as e:
            solo = f"ERROR {type(e).__name__}"
        still_gaming += solo == "gaming"
        matches_gold += solo == gold
        print(f"{solo:<14} gold={gold or '?':<14} {(title or '')[:60]}")
    print("\n" + "=" * 60)
    print(f"Still gaming when run solo: {still_gaming}/{len(rows)}")
    print(f"Solo label matches gold:    {matches_gold}/{len(rows)}")

if __name__ == "__main__":
    main()
