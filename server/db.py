import os

from psycopg_pool import ConnectionPool

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://mirror:mirror@localhost/algorithm_mirror",
)

# One shared pool for the whole app. Requests beyond 10 wait (up to 30s)
# instead of opening new connections and exhausting Postgres.
pool = ConnectionPool(DB_URL, min_size=1, max_size=10, timeout=30, open=True)


def query(sql: str, params: tuple):
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]