"""Pipeline status — reads pipeline_runs and data_quality_log."""
import pandas as pd
import plotly.express as px
import streamlit as st

from db import query

st.set_page_config(page_title="Pipeline Status", page_icon="🛠️", layout="wide")
st.title("🛠️ Pipeline Status")
st.caption("อ่านจากตาราง pipeline_runs และ data_quality_log ใน PostgreSQL (อัปเดตทุกครั้งที่ DAG รัน)")
if st.button("🔄 Refresh"):
    st.rerun()

runs = query("SELECT * FROM pipeline_runs ORDER BY id DESC LIMIT 2000")
if runs.empty:
    st.info("ยังไม่มีประวัติการรัน")
    st.stop()
for c in ("started_at", "finished_at"):
    runs[c] = pd.to_datetime(runs[c], utc=True).dt.tz_convert("Asia/Bangkok")

st.subheader("สถานะล่าสุดต่อแหล่งข้อมูล")
src = runs[runs["source"].isin(["air4thai", "openmeteo", "aqicn_scrape"])]
last_run_of_source = src.groupby("source")["run_id"].first()
cols = st.columns(3)
for col, name in zip(cols, ["air4thai", "openmeteo", "aqicn_scrape"]):
    if name not in last_run_of_source:
        col.metric(name, "never run")
        continue
    rows = src[(src["source"] == name) & (src["run_id"] == last_run_of_source[name])]
    ok = (rows["status"] == "success").all()
    failed = rows[rows["status"] != "success"]
    col.metric(name, "✅ success" if ok else ("⚠️ partial" if (rows["status"] == "success").any() else "❌ failed"),
               f"{int(rows['rows_fetched'].fillna(0).sum()):,} rows fetched", delta_color="off")
    col.caption(f"updated {rows['finished_at'].max():%d/%m/%Y %H:%M:%S} · {len(rows)} task(s)")
    if not failed.empty:
        col.error(failed["error_message"].iloc[0])

st.subheader("ผลตรวจคุณภาพข้อมูล + การตัดรายการซ้ำ")
dq = query("SELECT * FROM data_quality_log ORDER BY id DESC LIMIT 200")
if not dq.empty:
    dq["checked_at"] = pd.to_datetime(dq["checked_at"], utc=True).dt.tz_convert("Asia/Bangkok")
    last = dq.iloc[0]
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Quality check ล่าสุด", "✅ PASS" if last["passed"] else "❌ FAIL → quarantine")
    k2.metric("แถวหลัง dedupe", f"{int(last['total_rows']):,}")
    k3.metric("ตัดรายการซ้ำ", f"{int(last['duplicates_removed']):,}")
    k4.metric("PM2.5 null", f"{int(last['null_pm25']):,}")
    k5.metric("แหล่งที่ใช้ได้", last["sources_ok"] or "-")
    st.caption(f"{last['checked_at']:%d/%m/%Y %H:%M:%S} · {last['reasons']}")
    st.dataframe(dq, use_container_width=True, hide_index=True, height=250)

st.subheader("ประวัติการรันรายรอบ")
summary = (runs.groupby("run_id")
           .agg(started=("started_at", "min"), finished=("finished_at", "max"),
                tasks=("id", "count"), failed=("status", lambda s: int((s == "failed").sum())))
           .sort_values("started", ascending=False).reset_index())
st.dataframe(summary.head(50), use_container_width=True, hide_index=True)

hist = src.copy()
hist["run_hour"] = hist["finished_at"].dt.floor("h")
agg = hist.groupby(["run_hour", "source", "status"])["rows_fetched"].sum().reset_index()
fig = px.bar(agg, x="run_hour", y="rows_fetched", color="source", pattern_shape="status",
             labels={"run_hour": "รอบที่รัน", "rows_fetched": "rows fetched"}, barmode="group")
st.plotly_chart(fig, use_container_width=True)

st.subheader("Log ดิบ (pipeline_runs)")
st.dataframe(runs.head(300), use_container_width=True, hide_index=True, height=400)
