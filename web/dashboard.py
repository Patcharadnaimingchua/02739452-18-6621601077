"""แดชบอร์ด — PM2.5 รายชั่วโมงจากตาราง air_quality (PostgreSQL)."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st

import theme as t
from db import load_air_quality
from live import live_html

BKK = ZoneInfo("Asia/Bangkok")

t.header("ค่า PM2.5 รายชั่วโมง ทั่วประเทศไทย",
         "สถานีตรวจวัดจาก Air4Thai · Open-Meteo · aqicn.org — อ่านจาก PostgreSQL โดยตรง", live_html())

df = load_air_quality()
if df.empty:
    st.info("ยังไม่มีข้อมูล — รอ DAG air_quality_pipeline รันรอบแรก (Airflow http://localhost:8080) แล้วโหลดหน้าใหม่")
    st.stop()

# ---------------------------------------------------------------- sidebar filters
with st.sidebar:
    t.sidebar_group("ตัวกรอง")
    sel_prov = st.multiselect("จังหวัด", sorted(df["province"].unique()), placeholder="ทุกจังหวัด")
    t.sidebar_group("แหล่งข้อมูล")
    srcs = sorted(df["source"].unique(), key=lambda s: t.SOURCE_PRIORITY.get(s, 9))
    sel_src = [s for s in srcs if st.checkbox(t.SOURCE_LABEL.get(s, s), value=True, key=f"src_{s}")]
    t.sidebar_group("ช่วงเวลา")
    tmin, tmax = df["observed_at"].min().date(), df["observed_at"].max().date()
    date_range = st.date_input("ช่วงวันที่", value=(max(tmin, tmax - timedelta(days=2)), tmax),
                               min_value=tmin, max_value=tmax, label_visibility="collapsed")
    t.sidebar_group("ค่า PM2.5 (µg/m³)")
    pm_top = float(round(max(df["pm25"].max() or 0, 1) + 1))
    pm_range = st.slider("ช่วงค่า PM2.5", 0.0, pm_top, (0.0, pm_top), label_visibility="collapsed")
    include_null = st.checkbox("รวมแถวที่ไม่มีค่า PM2.5", value=False)
    st.write("")
    if st.button("โหลดข้อมูลใหม่"):
        st.cache_data.clear()
        st.rerun()

f = df[df["source"].isin(sel_src)]
if sel_prov:
    f = f[f["province"].isin(sel_prov)]
if isinstance(date_range, tuple) and len(date_range) == 2:
    f = f[(f["observed_at"].dt.date >= date_range[0]) & (f["observed_at"].dt.date <= date_range[1])]
f = f[f["pm25"].between(*pm_range) | (f["pm25"].isna() & include_null)]
valid = f.dropna(subset=["pm25"])


# ---------------------------------------------------------------- KPI row
def short(name, n=30):
    """Shorten at a word boundary with an ellipsis (never mid-word)."""
    name = str(name)
    if len(name) <= n:
        return name
    cut = name[:n].rsplit(" ", 1)[0].rstrip(",-·")
    return (cut or name[:n]) + "…"


def sparkline(values, width=220, height=34, color=t.ACCENT):
    """Tiny inline SVG line (sits inside the card; no axes, no toolbar, no extra JS)."""
    v = [x for x in values if x == x]
    if len(v) < 2:
        return ""
    lo, hi = min(v), max(v)
    span = (hi - lo) or 1
    step = width / (len(v) - 1)
    pts = " ".join(f"{i * step:.1f},{height - 3 - (x - lo) / span * (height - 6):.1f}" for i, x in enumerate(v))
    last_x, last_y = pts.split()[-1].split(",")
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" preserveAspectRatio="none" '
            f'style="display:block;margin-top:{t.SPACE}px"><polyline points="{pts}" fill="none" stroke="{color}" '
            f'stroke-width="1.5" vector-effect="non-scaling-stroke"/><circle cx="{last_x}" cy="{last_y}" r="2.5" '
            f'fill="{color}"/></svg>')


hourly = valid.set_index("observed_at")["pm25"].resample("h").mean().dropna()
cards = [t.kpi("จำนวนแถว", f"{len(f):,}", cmp_html=f"จากทั้งตาราง <b>{len(df):,}</b> แถว")]
if not valid.empty:
    avg = valid["pm25"].mean()
    lv = t.aqi_level(avg)
    if len(hourly) >= 2:
        d = hourly.iloc[-1] - hourly.iloc[-2]
        arrow = "▲" if d > 0 else ("▼" if d < 0 else "–")
        delta = f"{arrow} <b>{abs(d):.1f}</b> เทียบชั่วโมงก่อน ({hourly.index[-1]:%H:%M})"
    else:
        delta = "ยังไม่มีชั่วโมงก่อนหน้าให้เทียบ"
    spark = sparkline(hourly[hourly.index >= hourly.index.max() - timedelta(hours=24)].tolist())
    cards.append(t.kpi("PM2.5 เฉลี่ย", f"{avg:.1f}", "µg/m³", delta + spark, aqi=lv,
                       tag=(lv["label"], lv["color"], lv["fg"])))
    top = valid.loc[valid["pm25"].idxmax()]
    lv_top = t.aqi_level(top["pm25"])
    cards.append(t.kpi("PM2.5 สูงสุด", f"{top['pm25']:.1f}", "µg/m³",
                       f'<span class="muted">สูงสุดในช่วงที่เลือก</span><br><b>{t.esc(short(top["station_name"], 34))}</b><br>'
                       f"{t.esc(top['province'])} · {top['observed_at']:%d/%m %H:%M}",
                       aqi=lv_top, tag=(lv_top["label"], lv_top["color"], lv_top["fg"])))
else:
    cards.append(t.kpi("PM2.5 เฉลี่ย", "–", "µg/m³", "ไม่มีค่าในช่วงที่เลือก"))
    cards.append(t.kpi("PM2.5 สูงสุด", "–", "µg/m³", "สูงสุดในช่วงที่เลือก: ไม่มีค่า"))
cards.append(t.kpi("จำนวนสถานี", f"{f['station_id'].nunique():,}",
                   cmp_html=f"<b>{f['province'].nunique():,}</b> จังหวัด · <b>{f['source'].nunique()}</b> แหล่ง"))
if not f.empty:
    latest_ts = f["observed_at"].max()
    ingested = f["ingested_at"].max()
    age_min = max(0, int((datetime.now(BKK) - ingested).total_seconds() // 60))
    cards.append(t.kpi("ข้อมูลล่าสุด", f"{latest_ts:%H:%M}", latest_ts.strftime("%d/%m/%Y"),
                       f"ชั่วโมงล่าสุดของค่าที่วัด<br>นำเข้า {ingested:%H:%M} · <b>{age_min:,}</b> นาทีที่แล้ว"))
else:
    cards.append(t.kpi("ข้อมูลล่าสุด", "–"))
for col, card in zip(st.columns(5, gap="small"), cards):
    col.markdown(card, unsafe_allow_html=True)

if f.empty:
    st.warning("ไม่มีข้อมูลตามตัวกรองที่เลือก")
    st.stop()

# latest reading per station, preferring measured sources (Air4Thai) over model / scrape
latest = (valid.assign(_p=valid["source"].map(t.SOURCE_PRIORITY).fillna(9))
          .sort_values(["_p", "observed_at"], ascending=[True, False])
          .drop_duplicates("station_id").drop(columns="_p"))
latest["level"] = latest["pm25"].map(lambda v: t.aqi_level(v)["label"])
latest["src"] = latest["source"].map(t.SOURCE_LABEL)


# ---------------------------------------------------------------- charts
c1, c2 = st.columns([3, 2], gap="medium")
with c1:
    t.section("แนวโน้มรายชั่วโมง", "ค่าเฉลี่ยต่อแหล่ง")
    trend = valid.groupby([pd.Grouper(key="observed_at", freq="h"), "source"])["pm25"].mean().reset_index()
    trend["source"] = trend["source"].map(t.SOURCE_LABEL)
    fig = px.line(trend, x="observed_at", y="pm25", color="source", color_discrete_map=t.SOURCE_COLOR,
                  category_orders={"source": list(t.SOURCE_COLOR)}, labels={"observed_at": "", "pm25": "µg/m³"})
    fig.update_traces(line_width=2, mode="lines+markers", marker_size=4,
                      hovertemplate="%{y:.1f} µg/m³<extra>%{fullData.name}</extra>")
    fig.add_hline(y=t.THAI_STANDARD, line_dash="dash", line_width=1, line_color=t.MUTED,
                  annotation_text="มาตรฐานไทย 37.5", annotation_position="top left",
                  annotation_font=dict(size=10, color=t.TEXT_2))
    t.style_fig(fig, 360).update_layout(hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True, config=t.PLOT_CONFIG)
with c2:
    t.section("10 สถานีที่ฝุ่นสูงสุด", "ค่าล่าสุดของแต่ละสถานี")
    top10 = latest.nlargest(10, "pm25").sort_values("pm25")
    top10["label"] = top10["station_name"].map(short)
    top10.loc[top10["label"].duplicated(keep=False), "label"] += " · " + top10["station_id"]
    fig = px.bar(top10, x="pm25", y="label", orientation="h", color="level",
                 color_discrete_map=t.AQI_COLOR_MAP, category_orders={"level": t.AQI_ORDER},
                 text="pm25", custom_data=["station_name", "province", "observed_at", "src"],
                 labels={"pm25": "µg/m³", "label": ""})
    fig.update_traces(texttemplate="%{x:.1f}", textposition="outside", cliponaxis=False, width=0.7,
                      textfont=dict(size=11, color=t.TEXT),
                      hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]} · %{customdata[3]}<br>"
                                    "%{x:.1f} µg/m³ · %{customdata[2]|%d/%m %H:%M}<extra></extra>")
    t.style_fig(fig, 360, legend=False).update_layout(
        xaxis_range=[0, top10["pm25"].max() * 1.2], bargap=0.3,
        yaxis=dict(categoryorder="array", categoryarray=top10["label"].tolist(), showgrid=False))
    st.plotly_chart(fig, use_container_width=True, config=t.PLOT_CONFIG)

t.section("แผนที่สถานี", "ค่าล่าสุดของแต่ละสถานี")
t.aqi_legend()
geo = latest.dropna(subset=["lat", "lon"])
fig = px.scatter_mapbox(geo, lat="lat", lon="lon", color="level", color_discrete_map=t.AQI_COLOR_MAP,
                        category_orders={"level": t.AQI_ORDER},
                        custom_data=["station_name", "province", "pm25", "observed_at", "src"],
                        zoom=4.8, center={"lat": 13.0, "lon": 101.0}, height=560)
fig.update_traces(marker=dict(size=10, opacity=0.9),
                  hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]} · %{customdata[4]}<br>"
                                "PM2.5 %{customdata[2]:.1f} µg/m³ · %{customdata[3]|%d/%m %H:%M}<extra></extra>")
t.style_fig(fig, legend=False).update_layout(mapbox_style=t.MAP_STYLE, mapbox_layers=t.MAP_LAYERS,
                                            margin=dict(l=0, r=0, t=0, b=0))
st.plotly_chart(fig, use_container_width=True, config=t.PLOT_CONFIG)

t.section("ตารางข้อมูล", f"{len(f):,} แถว")
show = f.sort_values(["observed_at", "pm25"], ascending=[False, False]).copy()
show["source"] = show["source"].map(t.SOURCE_LABEL)
st.dataframe(
    show, use_container_width=True, hide_index=True, height=420,
    column_order=["observed_at", "station_name", "province", "pm25", "source", "station_id", "lat", "lon", "ingested_at"],
    column_config={
        "observed_at": st.column_config.DatetimeColumn("เวลา", format="DD/MM/YYYY HH:mm", width="medium"),
        "station_name": st.column_config.TextColumn("สถานี", width="large"),
        "province": st.column_config.TextColumn("จังหวัด", width="small"),
        "pm25": st.column_config.ProgressColumn("PM2.5 (µg/m³)", format="%.1f", min_value=0,
                                                max_value=float(max(show["pm25"].max() or 0, 75)), width="medium"),
        "source": st.column_config.TextColumn("แหล่ง", width="small"),
        "station_id": st.column_config.TextColumn("รหัสสถานี", width="small"),
        "lat": st.column_config.NumberColumn("lat", format="%.4f", width="small"),
        "lon": st.column_config.NumberColumn("lon", format="%.4f", width="small"),
        "ingested_at": st.column_config.DatetimeColumn("นำเข้าเมื่อ", format="DD/MM HH:mm", width="small"),
    })
st.download_button("ดาวน์โหลด CSV", show.to_csv(index=False).encode("utf-8-sig"), "pm25_filtered.csv", "text/csv")
