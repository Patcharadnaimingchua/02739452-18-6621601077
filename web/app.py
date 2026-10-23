"""PM2.5 dashboard — reads air_quality directly from PostgreSQL."""
from datetime import timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from db import query

st.set_page_config(page_title="Thailand PM2.5 Dashboard", page_icon="🌫️", layout="wide")
st.title("🌫️ ค่า PM2.5 รายชั่วโมง — สถานีตรวจวัดคุณภาพอากาศทั่วประเทศไทย")
st.caption("02739452 แพลตฟอร์มข้อมูลขนาดใหญ่และการวิเคราะห์ · นายพชรดนัย มิ่งเชื้อ 6621601077 หมู่ 700 · "
           "แหล่งข้อมูล: Air4Thai (คพ.), Open-Meteo Air Quality, aqicn.org (scrape)")

SOURCE_LABEL = {"air4thai": "Air4Thai (API)", "openmeteo": "Open-Meteo (API)", "aqicn_scrape": "aqicn.org (scrape)"}


@st.cache_data(ttl=60)
def load():
    df = query("""SELECT station_id, station_name, province, lat, lon, pm25, observed_at, source, ingested_at
                  FROM air_quality ORDER BY observed_at""")
    if not df.empty:
        df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True).dt.tz_convert("Asia/Bangkok")
        df["province"] = df["province"].fillna("(unknown)")
    return df


df = load()
if df.empty:
    st.info("ยังไม่มีข้อมูล — รอ DAG `air_quality_pipeline` รันครั้งแรก (Airflow http://localhost:8080) แล้วกด Rerun")
    st.stop()

# ---------------------------------------------------------------- filters
with st.sidebar:
    st.header("ตัวกรอง")
    provinces = sorted(df["province"].unique())
    sel_prov = st.multiselect("จังหวัด", provinces, placeholder="ทั้งหมด")
    srcs = sorted(df["source"].unique())
    sel_src = st.multiselect("แหล่งข้อมูล", srcs, default=srcs, format_func=lambda s: SOURCE_LABEL.get(s, s))
    tmin, tmax = df["observed_at"].min().date(), df["observed_at"].max().date()
    date_range = st.date_input("ช่วงวันที่", value=(max(tmin, tmax - timedelta(days=2)), tmax),
                               min_value=tmin, max_value=tmax)
    pm_max = float(max(df["pm25"].max() or 0, 1))
    pm_range = st.slider("ช่วงค่า PM2.5 (µg/m³)", 0.0, float(round(pm_max + 1)), (0.0, float(round(pm_max + 1))))
    include_null = st.checkbox("รวมแถวที่ไม่มีค่า PM2.5", value=False)
    if st.button("🔄 Reload data"):
        st.cache_data.clear()
        st.rerun()

f = df[df["source"].isin(sel_src)]
if sel_prov:
    f = f[f["province"].isin(sel_prov)]
if isinstance(date_range, tuple) and len(date_range) == 2:
    d0, d1 = date_range
    f = f[(f["observed_at"].dt.date >= d0) & (f["observed_at"].dt.date <= d1)]
in_range = f["pm25"].between(*pm_range)
f = f[in_range | (f["pm25"].isna() & include_null)]

# ---------------------------------------------------------------- KPIs
valid = f.dropna(subset=["pm25"])
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("จำนวนแถว", f"{len(f):,}", help=f"ทั้งตาราง {len(df):,} แถว")
c2.metric("PM2.5 เฉลี่ย", f"{valid['pm25'].mean():.1f} µg/m³" if not valid.empty else "-")
if not valid.empty:
    top = valid.loc[valid["pm25"].idxmax()]
    c3.metric("PM2.5 สูงสุด", f"{top['pm25']:.1f} µg/m³")
    c3.caption(f"{top['station_name']} ({top['province']}) · {top['observed_at']:%d/%m %H:%M}")
else:
    c3.metric("PM2.5 สูงสุด", "-")
c4.metric("จำนวนสถานี", f"{f['station_id'].nunique():,}")
c5.metric("เวลาข้อมูลล่าสุด", f"{f['observed_at'].max():%d/%m/%Y %H:%M}" if not f.empty else "-")

if f.empty:
    st.warning("ไม่มีข้อมูลตามตัวกรอง")
    st.stop()

# ---------------------------------------------------------------- charts
left, right = st.columns([3, 2])
with left:
    st.subheader("แนวโน้ม PM2.5 เฉลี่ยรายชั่วโมง")
    trend = (valid.groupby([pd.Grouper(key="observed_at", freq="h"), "source"])["pm25"].mean()
             .reset_index())
    trend["source"] = trend["source"].map(lambda s: SOURCE_LABEL.get(s, s))
    fig = px.line(trend, x="observed_at", y="pm25", color="source", markers=True,
                  labels={"observed_at": "เวลา (Asia/Bangkok)", "pm25": "PM2.5 (µg/m³)", "source": "แหล่ง"})
    fig.add_hline(y=37.5, line_dash="dot", annotation_text="มาตรฐานไทย 37.5 µg/m³ (เฉลี่ย 24 ชม.)")
    st.plotly_chart(fig, use_container_width=True)
with right:
    st.subheader("Top 10 สถานีที่ฝุ่นสูงสุด (ค่าล่าสุด)")
    latest = valid.sort_values("observed_at").groupby("station_id").tail(1)
    top10 = latest.nlargest(10, "pm25").sort_values("pm25")
    fig = px.bar(top10, x="pm25", y="station_name", orientation="h", color="pm25",
                 color_continuous_scale="YlOrRd", hover_data=["province", "observed_at", "source"],
                 labels={"pm25": "PM2.5 (µg/m³)", "station_name": ""})
    fig.update_layout(coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)

st.subheader("แผนที่สถานี (ค่าล่าสุดของแต่ละสถานี)")
geo = latest.dropna(subset=["lat", "lon"])
fig = px.scatter_mapbox(geo, lat="lat", lon="lon", color="pm25", size=geo["pm25"].clip(lower=3),
                        color_continuous_scale="YlOrRd", range_color=(0, max(75, geo["pm25"].max())),
                        hover_name="station_name", hover_data=["province", "pm25", "observed_at", "source"],
                        zoom=4.6, center={"lat": 13.0, "lon": 101.0}, height=600)
fig.update_layout(mapbox_style="open-street-map", margin=dict(l=0, r=0, t=0, b=0))
st.plotly_chart(fig, use_container_width=True)

st.subheader("ตารางข้อมูล")
show = f.sort_values(["observed_at", "pm25"], ascending=[False, False]).copy()
show["source"] = show["source"].map(lambda s: SOURCE_LABEL.get(s, s))
st.dataframe(show, use_container_width=True, hide_index=True, height=420,
             column_config={"observed_at": st.column_config.DatetimeColumn("observed_at", format="YYYY-MM-DD HH:mm"),
                            "ingested_at": st.column_config.DatetimeColumn("ingested_at", format="YYYY-MM-DD HH:mm")})
st.download_button("ดาวน์โหลด CSV", show.to_csv(index=False).encode("utf-8-sig"), "pm25_filtered.csv", "text/csv")
