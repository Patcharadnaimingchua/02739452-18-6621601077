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
