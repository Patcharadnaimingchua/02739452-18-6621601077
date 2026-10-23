"""สถานะ Pipeline — อ่านตาราง pipeline_runs และ data_quality_log."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import theme as t
from db import SOURCES, load_runs, query, run_status
from live import live_html

t.header("สถานะ Pipeline", "DAG air_quality_pipeline · ตาราง pipeline_runs และ data_quality_log", live_html())

runs = load_runs()
if runs.empty:
    st.info("ยังไม่มีประวัติการรัน")
    st.stop()

with st.sidebar:
    t.sidebar_group("ข้อมูล")
    if st.button("โหลดข้อมูลใหม่"):
        st.cache_data.clear()
        st.rerun()

# ---------------------------------------------------------------- per-source cards
t.section("แหล่งข้อมูล", "รอบล่าสุดของแต่ละแหล่ง")
src_rows = runs[runs["source"].isin(SOURCES)]
for col, name in zip(st.columns(3, gap="small"), SOURCES):
    rows = src_rows[src_rows["source"] == name]
    if rows.empty:
        col.markdown(f'<div class="card"><div class="src-head"><b>{t.SOURCE_LABEL[name]}</b>{t.badge("never")}</div></div>',
                     unsafe_allow_html=True)
        continue
    rows = rows[rows["run_id"] == rows.iloc[0]["run_id"]]
    n_ok = int((rows["status"] == "success").sum())
    status = "success" if n_ok == len(rows) else ("partial" if n_ok else "failed")
    err = rows.loc[rows["status"] != "success", "error_message"].dropna()
    err_html = f'<div class="err">{t.esc(err.iloc[0][:220])}</div>' if not err.empty else ""
    col.markdown(
        f'<div class="card"><div class="src-head"><b>{t.SOURCE_LABEL[name]}</b>{t.badge(status)}</div>'
        f'<div class="val">{int(rows["rows_fetched"].fillna(0).sum()):,}<small>rows fetched</small></div>'
        f'<div class="cmp">อัปเดต {rows["finished_at"].max():%d/%m %H:%M:%S} · {len(rows)} task · '
        f'{t.esc(rows.iloc[0]["run_id"])}</div>{err_html}</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------- data quality
t.section("ผลตรวจคุณภาพข้อมูล", "รอบล่าสุด")
dq = query("SELECT * FROM data_quality_log ORDER BY id DESC LIMIT 200")
if not dq.empty:
    dq["checked_at"] = pd.to_datetime(dq["checked_at"], utc=True).dt.tz_convert("Asia/Bangkok")
    last = dq.iloc[0]
    ok = bool(last["passed"])
    verdict = t.badge("success" if ok else "quarantined", "PASS" if ok else "FAIL")
    cards = [
        t.kpi("Quality check", verdict, cmp_html=f"{last['checked_at']:%d/%m %H:%M} · "
              f"{'→ load_upsert' if ok else '→ quarantine'}<br>{t.esc(last['reasons'])}"),
        t.kpi("แถวหลัง dedupe", f"{int(last['total_rows']):,}", cmp_html=f"แหล่งที่ใช้ได้ <b>{t.esc(last['sources_ok'] or '-')}</b>"),
        t.kpi("ตัดรายการซ้ำ", f"{int(last['duplicates_removed']):,}", cmp_html="ข้ามแหล่ง · พิกัด + ชั่วโมง"),
        t.kpi("PM2.5 null", f"{int(last['null_pm25']):,}", cmp_html="เกณฑ์ ≤ 30% ของแถว"),
        t.kpi("นอกช่วง / นอกประเทศ", f"{int(last['out_of_range'])} / {int(last['out_of_thailand'])}",
              cmp_html="pm25 0–1000 · กรอบพิกัดไทย"),
    ]
    for col, card in zip(st.columns(5, gap="small"), cards):
        col.markdown(card, unsafe_allow_html=True)

# ---------------------------------------------------------------- run timeline
t.section("ไทม์ไลน์การรัน", "หนึ่งจุดต่อหนึ่งรอบ")
summary = []
for rid, rows in runs.groupby("run_id"):
    loaded = rows.loc[rows["source"].isin(["load_upsert", "quality_alert"]), "rows_fetched"]
    started, finished = rows["started_at"].min(), rows["finished_at"].max()
    summary.append({"run_id": rid, "status": run_status(rows), "started": started, "finished": finished,
                    "duration_s": (finished - started).total_seconds() if pd.notna(started) else None,
                    "rows": int(loaded.iloc[0]) if not loaded.empty else None,
                    "failed_tasks": int((rows["status"] == "failed").sum())})
summary = pd.DataFrame(summary).sort_values("started", ascending=False)

fig = go.Figure()
for status in ["success", "partial", "quarantined", "failed"]:
    s = summary[summary["status"] == status]
    if s.empty:
        continue
    fig.add_trace(go.Scatter(
        x=s["started"], y=[0] * len(s), mode="markers", name=t.STATUS_LABEL[status],
        marker=dict(size=14, symbol="square", color=t.STATUS_COLOR[status], line=dict(width=0)),
        customdata=s[["run_id", "duration_s", "rows", "failed_tasks"]].fillna(0).values,
        hovertemplate="<b>%{customdata[0]}</b><br>%{x|%d/%m %H:%M}<br>ใช้เวลา %{customdata[1]:.0f} วินาที"
                      "<br>แถว %{customdata[2]:,} · task ล้มเหลว %{customdata[3]}<extra></extra>"))
t.style_fig(fig, 150).update_layout(yaxis=dict(visible=False, range=[-1, 1]), hovermode="closest")
st.plotly_chart(fig, use_container_width=True, config=t.PLOT_CONFIG)

hist = src_rows.assign(run_hour=src_rows["finished_at"].dt.floor("h"), source=src_rows["source"].map(t.SOURCE_LABEL))
agg = hist.groupby(["run_hour", "source", "status"])["rows_fetched"].sum().reset_index()
t.section("จำนวนแถวที่ดึงต่อแหล่ง", "รวมต่อชั่วโมงที่รัน")
fig = px.bar(agg, x="run_hour", y="rows_fetched", color="source", pattern_shape="status", barmode="group",
             color_discrete_map=t.SOURCE_COLOR, labels={"run_hour": "", "rows_fetched": "rows"})
st.plotly_chart(t.style_fig(fig, 280), use_container_width=True, config=t.PLOT_CONFIG)

# ---------------------------------------------------------------- tables
with st.expander(f"ประวัติการรันรายรอบ ({len(summary)} รอบ)"):
    st.dataframe(summary, use_container_width=True, hide_index=True, column_config={
        "started": st.column_config.DatetimeColumn("เริ่ม", format="DD/MM HH:mm:ss"),
        "finished": st.column_config.DatetimeColumn("จบ", format="DD/MM HH:mm:ss"),
        "duration_s": st.column_config.NumberColumn("วินาที", format="%.0f"),
        "rows": st.column_config.NumberColumn("แถวที่โหลด", format="%d"),
    })
with st.expander("ผลตรวจคุณภาพทั้งหมด (data_quality_log)"):
    st.dataframe(dq, use_container_width=True, hide_index=True)
with st.expander("Log ดิบ (pipeline_runs)"):
    st.dataframe(runs.head(300), use_container_width=True, hide_index=True)
