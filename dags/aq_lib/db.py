"""PostgreSQL helpers for the airquality database (credentials come from env, never hard-coded)."""
import os
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import execute_values

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS air_quality (
    station_id   TEXT        NOT NULL,
    station_name TEXT,
    province     TEXT,
    lat          DOUBLE PRECISION,
    lon          DOUBLE PRECISION,
    pm25         DOUBLE PRECISION,
    observed_at  TIMESTAMPTZ NOT NULL,
    source       TEXT        NOT NULL,
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (station_id, observed_at)
);
CREATE INDEX IF NOT EXISTS idx_aq_observed ON air_quality (observed_at);
CREATE INDEX IF NOT EXISTS idx_aq_source ON air_quality (source);
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id            BIGSERIAL PRIMARY KEY,
    run_id        TEXT NOT NULL,
    source        TEXT NOT NULL,
    status        TEXT NOT NULL,
    rows_fetched  INTEGER,
    error_message TEXT,
    detail        TEXT,
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_runs_run ON pipeline_runs (run_id);
CREATE TABLE IF NOT EXISTS data_quality_log (
    id                 BIGSERIAL PRIMARY KEY,
    run_id             TEXT NOT NULL,
    checked_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    passed             BOOLEAN NOT NULL,
    total_rows         INTEGER,
    duplicates_removed INTEGER,
    null_pm25          INTEGER,
    out_of_range       INTEGER,
    out_of_thailand    INTEGER,
    sources_ok         TEXT,
    reasons            TEXT,
    action             TEXT
);
CREATE TABLE IF NOT EXISTS air_quality_quarantine (
    id             BIGSERIAL PRIMARY KEY,
    run_id         TEXT NOT NULL,
    quarantined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reasons        TEXT,
    row_count      INTEGER,
    sample         JSONB
);
"""

# Lower number wins when the same station/hour arrives from several sources.
SOURCE_PRIORITY = {"air4thai": 1, "openmeteo": 2, "aqicn_scrape": 3}

UPSERT_SQL = """
INSERT INTO air_quality AS t
    (station_id, station_name, province, lat, lon, pm25, observed_at, source, ingested_at)
VALUES %s
ON CONFLICT (station_id, observed_at) DO UPDATE SET
    station_name = EXCLUDED.station_name,
    province     = EXCLUDED.province,
    lat          = EXCLUDED.lat,
    lon          = EXCLUDED.lon,
    pm25         = EXCLUDED.pm25,
    source       = EXCLUDED.source,
    ingested_at  = EXCLUDED.ingested_at
WHERE (CASE EXCLUDED.source WHEN 'air4thai' THEN 1 WHEN 'openmeteo' THEN 2 ELSE 3 END)
   <= (CASE t.source        WHEN 'air4thai' THEN 1 WHEN 'openmeteo' THEN 2 ELSE 3 END)
"""


@contextmanager
def connect():
    conn = psycopg2.connect(
        host=os.environ.get("AQ_DB_HOST", "postgres"),
        port=int(os.environ.get("AQ_DB_PORT", "5432")),
        dbname=os.environ.get("AQ_DB_NAME", "airquality"),
        user=os.environ.get("AQ_DB_USER", "airflow"),
        password=os.environ.get("AQ_DB_PASSWORD", ""),
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_schema():
    with connect() as conn, conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)


def log_run(run_id, source, status, rows_fetched=None, error_message=None, detail=None, started_at=None):
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO pipeline_runs
               (run_id, source, status, rows_fetched, error_message, detail, started_at, finished_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (run_id, source, status, rows_fetched, error_message, detail,
             started_at, datetime.now(timezone.utc)),
        )


def upsert_air_quality(records):
    """records: list of dicts in the unified schema. Returns (rows sent, table count after)."""
    now = datetime.now(timezone.utc)
    values = [
        (r["station_id"], r["station_name"], r["province"], r["lat"], r["lon"],
         r["pm25"], r["observed_at"], r["source"], now)
        for r in records
    ]
    with connect() as conn, conn.cursor() as cur:
        execute_values(cur, UPSERT_SQL, values, page_size=1000)
        cur.execute("SELECT COUNT(*) FROM air_quality")
        total = cur.fetchone()[0]
    return len(values), total
