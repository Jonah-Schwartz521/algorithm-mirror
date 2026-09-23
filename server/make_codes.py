"""Create study codes to hand out.   python make_codes.py 10"""
import os
import secrets
import sys

import psycopg

DB_URL = os.environ.get("DATABASE_URL", "postgresql://mirror:mirror@localhost/algorithm_mirror")
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I to avoid typos


def main(n):
    with psycopg.connect(DB_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT COALESCE(MAX(SUBSTRING(study_code FROM 2 FOR 2)::int), 0) FROM participants "
                    "WHERE study_code ~ '^P[0-9]{2}-'")
        start = cur.fetchone()[0] + 1
        codes = []
        for i in range(start, start + n):
            code = f"P{i:02d}-" + "".join(secrets.choice(ALPHABET) for _ in range(4))
            cur.execute("INSERT INTO participants (study_code) VALUES (%s)", (code,))
            codes.append(code)
    print("New study codes (put a name next to each in your private team sheet):")
    for c in codes:
        print(" ", c)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
