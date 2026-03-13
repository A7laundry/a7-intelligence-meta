"""PostgreSQL adapter that provides a sqlite3-compatible interface.

All 35 service files call get_connection() and use:
  - conn.execute(sql, params) with ? placeholders
  - conn.fetchone() / conn.fetchall() returning dict-like rows
  - conn.commit() / conn.close()
  - row["column_name"] access

This adapter translates all of that transparently.
"""

import re
import time
import logging
import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)


def _sqlite_to_pg_sql(sql: str) -> str:
    """Convert SQLite SQL dialect to PostgreSQL."""
    # Replace ? placeholders with %s
    sql = sql.replace("?", "%s")
    # Replace AUTOINCREMENT with nothing (PostgreSQL uses SERIAL)
    sql = re.sub(r'\bAUTOINCREMENT\b', '', sql, flags=re.IGNORECASE)
    # Replace INTEGER PRIMARY KEY with SERIAL PRIMARY KEY (only in CREATE TABLE)
    sql = re.sub(
        r'\bINTEGER\s+PRIMARY\s+KEY\b',
        'SERIAL PRIMARY KEY',
        sql, flags=re.IGNORECASE
    )
    # Replace SQLite datetime functions
    sql = sql.replace("datetime('now')", "NOW()")
    sql = sql.replace("date('now')", "CURRENT_DATE")
    # Replace SQLite-specific PRAGMA (skip these)
    if re.match(r'\s*PRAGMA\s+', sql, re.IGNORECASE):
        return ""
    # Replace sqlite_master references
    sql = sql.replace("sqlite_master", "information_schema.tables")
    return sql


class PostgresRow(dict):
    """Dict-like row that also supports index access."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class PostgresCursor:
    """Wraps psycopg2 cursor to provide sqlite3-compatible interface."""

    def __init__(self, cursor):
        self._cursor = cursor
        self._last_sql = ""

    def execute(self, sql, params=None):
        converted = _sqlite_to_pg_sql(sql)
        if not converted.strip():
            return self  # skip PRAGMA etc.
        if params:
            # Convert tuple params to list for psycopg2
            self._cursor.execute(converted, list(params))
        else:
            self._cursor.execute(converted)
        return self

    def executemany(self, sql, seq_params):
        converted = _sqlite_to_pg_sql(sql)
        if not converted.strip():
            return self
        self._cursor.executemany(converted, seq_params)
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return PostgresRow(row)

    def fetchall(self):
        rows = self._cursor.fetchall()
        return [PostgresRow(r) for r in rows]

    @property
    def lastrowid(self):
        if self._cursor.rowcount > 0:
            try:
                self._cursor.execute("SELECT lastval()")
                row = self._cursor.fetchone()
                if row is None:
                    return None
                # RealDictCursor returns dict-like rows; access by column name
                if hasattr(row, "keys"):
                    return list(row.values())[0]
                return row[0]
            except Exception:
                return None
        return None

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def __iter__(self):
        for row in self._cursor:
            yield PostgresRow(row)


class PostgresConnection:
    """Wraps psycopg2 connection to provide sqlite3-compatible interface."""

    def __init__(self, dsn: str, max_retries: int = 3, retry_delay: float = 1.0):
        last_exc = None
        for attempt in range(max_retries):
            try:
                self._conn = psycopg2.connect(
                    dsn,
                    cursor_factory=psycopg2.extras.RealDictCursor,
                    connect_timeout=10,
                )
                self._conn.autocommit = False
                self._cursor = PostgresCursor(self._conn.cursor())
                return
            except psycopg2.OperationalError as exc:
                last_exc = exc
                if attempt < max_retries - 1:
                    logger.warning(
                        "[postgres] Connection attempt %d/%d failed: %s — retrying in %.1fs",
                        attempt + 1, max_retries, exc, retry_delay
                    )
                    time.sleep(retry_delay)
        raise last_exc

    def execute(self, sql, params=None):
        return self._cursor.execute(sql, params)

    def executemany(self, sql, seq_params):
        return self._cursor.executemany(sql, seq_params)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        try:
            self._cursor._cursor.close()
            self._conn.close()
        except Exception:
            pass

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()
