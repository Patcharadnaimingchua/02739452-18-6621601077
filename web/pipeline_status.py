"""Pipeline status — reads pipeline_runs and data_quality_log."""
import pandas as pd
import plotly.express as px
import streamlit as st

import theme
from db import query
from theme import STATUS_STYLE

theme.inject_css()
theme.header("สถานะ Pipeline", "อ่านจากตาราง pipeline_runs และ data_quality_log ใน PostgreSQL · อัปเดตทุกครั้งที่ DAG air_quality_pipeline รัน")
with st.sidebar:
    if st.button("รีเฟรช"):
        st.rerun()

runs = query("SELECT * FROM pipeline_runs ORDER BY id DESC LIMIT 2000")
if runs.empty:
    st.info("ยังไม่มีประวัติการรัน")
    st.stop()
for c in ("started_at", "finished_at"):
    runs[c] = pd.to_datetime(runs[c], utc=True).dt.tz_convert("Asia/Bangkok")


def color_status(v):
    fg, bg, _ = STATUS_STYLE.get(v, STATUS_STYLE["skipped"])
    return f"color:{fg};background-color:{bg};font-weight:600"


theme.section("สถานะล่าสุดต่อแหล่งข้อมูล")
SOURCES = {"air4thai": "Air4Thai (API)", "openmeteo": "Open-Meteo (API)", "aqicn_scrape": "aqicn.org (scrape)"}
src = runs[runs["source"].isin(SOURCES)]
last_run_of_source = src.groupby("source")["run_id"].first()
cols = st.columns(3, gap="medium")
for col, name in zip(cols, SOURCES):
    if name not in last_run_of_source:
        col.markdown(f'<div class="src-card"><div class="name">{SOURCES[name]}</div>'
                     f'<div style="margin-top:8px">{theme.badge("never")}</div></div>', unsafe_allow_html=True)
        continue
    rows = src[(src["source"] == name) & (src["run_id"] == last_run_of_source[name])]
    n_ok = int((rows["status"] == "success").sum())
    status = "success" if n_ok == len(rows) else ("partial" if n_ok else "failed")
    failed = rows[rows["status"] != "success"]
    err = (f'<div class="err">{failed["error_message"].iloc[0]}</div>' if not failed.empty else "")
    col.markdown(
        f'<div class="src-card"><div style="display:flex;justify-content:space-between;align-items:center;gap:8px">'
        f'<span class="name">{SOURCES[name]}</span>{theme.badge(status)}</div>'
        f'<div class="big">{int(rows["rows_fetched"].fillna(0).sum()):,} <small style="font-size:.8rem">rows fetched</small></div>'
        f'<div class="meta">อัปเดต {rows["finished_at"].max():%d/%m/%Y %H:%M:%S} · {len(rows)} task(s)<br>'
        f'run: {last_run_of_source[name]}</div>{err}</div>', unsafe_allow_html=True)

theme.section("ผลตรวจคุณภาพข้อมูล + การตัดรายการซ้ำ")
dq = query("SELECT * FROM data_quality_log ORDER BY id DESC LIMIT 200")
if not dq.empty:
    dq["checked_at"] = pd.to_datetime(dq["checked_at"], utc=True).dt.tz_convert("Asia/Bangkok")
    last = dq.iloc[0]
    ok = bool(last["passed"])
    theme.kpi_row([
        theme.kpi_card("Quality check ล่าสุด", "PASS" if ok else "FAIL",
                       tag=("→ load_upsert", "#dcfce7", "#166534") if ok else ("→ quarantine", "#fef3c7", "#92400e"),
                       foot=f"{last['checked_at']:%d/%m %H:%M:%S}"),
        theme.kpi_card("แถวหลัง dedupe", f"{int(last['total_rows']):,}"),
        theme.kpi_card("ตัดรายการซ้ำ", f"{int(last['duplicates_removed']):,}", foot="ข้ามแหล่ง (พิกัด+ชั่วโมง)"),
        theme.kpi_card("PM2.5 null", f"{int(last['null_pm25']):,}"),
        theme.kpi_card("แหล่งที่ใช้ได้", str(len((last["sources_ok"] or "").split(",")) if last["sources_ok"] else 0) + "/3",
                       foot=last["sources_ok"] or "-"),
    ])
    st.caption(f"เหตุผล: {last['reasons']}")
    dq_view = dq.assign(result=dq["passed"].map({True: "success", False: "quarantined"}))
    st.dataframe(dq_view.style.map(color_status, subset=["result"]), use_container_width=True, hide_index=True, height=250)

theme.section("ประวัติการรันรายรอบ")
summary = (runs.groupby("run_id")
           .agg(started=("started_at", "min"), finished=("finished_at", "max"),
                tasks=("id", "count"), failed=("status", lambda s: int((s == "failed").sum())),
                quarantined=("status", lambda s: int((s == "quarantined").sum())))
           .sort_values("started", ascending=False).reset_index())
summary["status"] = summary.apply(lambda r: "quarantined" if r["quarantined"] else ("failed" if r["failed"] else "success"),
                                  axis=1)
summary["status"] = summary["status"].where(summary["status"] != "failed", "partial")
st.dataframe(summary.head(50).style.map(color_status, subset=["status"]), use_container_width=True, hide_index=True)
st.caption("partial = มีบางแหล่งล้มเหลว แต่ DAG ยังรวมข้อมูลจากแหล่งที่เหลือได้ (none_failed_min_one_success)")

hist = src.copy()
hist["run_hour"] = hist["finished_at"].dt.floor("h")
hist["source"] = hist["source"].map(SOURCES)
agg = hist.groupby(["run_hour", "source", "status"])["rows_fetched"].sum().reset_index()
fig = px.bar(agg, x="run_hour", y="rows_fetched", color="source", pattern_shape="status",
             color_discrete_map=theme.SOURCE_COLOR, barmode="group",
             labels={"run_hour": "รอบที่รัน", "rows_fetched": "rows fetched", "source": "แหล่ง", "status": "สถานะ"})
st.plotly_chart(theme.style_fig(fig, 360), use_container_width=True)

theme.section("Log ดิบ (pipeline_runs)")
st.dataframe(runs.head(300).style.map(color_status, subset=["status"]), use_container_width=True, hide_index=True,
             height=400)
