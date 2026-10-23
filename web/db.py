import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


@st.cache_resource
def engine():
    url = URL.create(
        "postgresql+psycopg2",
        username=os.environ.get("AQ_DB_USER", "airflow"),
        password=os.environ.get("AQ_DB_PASSWORD", ""),
        host=os.environ.get("AQ_DB_HOST", "postgres"),
        port=int(os.environ.get("AQ_DB_PORT", "5432")),
        database=os.environ.get("AQ_DB_NAME", "airquality"),
    )
    return create_engine(url, pool_pre_ping=True)


def query(sql, **params):
    """Read straight from PostgreSQL; returns an empty frame if tables do not exist yet."""
    try:
        with engine().connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)
    except Exception as exc:  # noqa: BLE001
        st.warning(f"ยังอ่านข้อมูลไม่ได้ (DAG อาจยังไม่รันครั้งแรก): {type(exc).__name__}")
        return pd.DataFrame()


@st.cache_data(ttl=60, show_spinner=False)
def load_air_quality():
    df = query("""SELECT station_id, station_name, province, lat, lon, pm25, observed_at, source, ingested_at
                  FROM air_quality ORDER BY observed_at""")
    if not df.empty:
        df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True).dt.tz_convert("Asia/Bangkok")
        df["ingested_at"] = pd.to_datetime(df["ingested_at"], utc=True).dt.tz_convert("Asia/Bangkok")
        df["province"] = df["province"].fillna("(ไม่ระบุ)")
    return df


@st.cache_data(ttl=30, show_spinner=False)
def load_runs(limit=3000):
    runs = query("SELECT * FROM pipeline_runs ORDER BY id DESC LIMIT :n", n=limit)
    for c in ("started_at", "finished_at"):
        if c in runs:
            runs[c] = pd.to_datetime(runs[c], utc=True).dt.tz_convert("Asia/Bangkok")
    return runs


SOURCES = ("air4thai", "openmeteo", "aqicn_scrape")


def run_status(rows):
    """Overall status of one DAG run from its pipeline_runs rows."""
    s = set(rows["status"])
    if "quarantined" in s:
        return "quarantined"
    src = rows[rows["source"].isin(SOURCES)]
    if not src.empty and (src["status"] == "success").sum() == 0:
        return "failed"
    if "failed" in s:
        return "partial"
    return "success"


def latest_run_status():
    """(status, finished_at) of the most recent DAG run, or (None, None)."""
    runs = load_runs()
    if runs.empty:
        return None, None
    rid = runs.iloc[0]["run_id"]
    rows = runs[runs["run_id"] == rid]
    return run_status(rows), rows["finished_at"].max()
