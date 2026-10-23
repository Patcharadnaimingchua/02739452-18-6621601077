"""PM2.5 dashboard — reads air_quality directly from PostgreSQL."""
from datetime import timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

import theme
from db import query
from theme import AQI_COLOR_MAP, AQI_ORDER, SOURCE_COLOR, SOURCE_LABEL, SOURCE_PRIORITY

theme.inject_css()
theme.header("ค่า PM2.5 รายชั่วโมง สถานีตรวจวัดคุณภาพอากาศทั่วประเทศไทย",
             "02739452 แพลตฟอร์มข้อมูลขนาดใหญ่และการวิเคราะห์ · นายพชรดนัย มิ่งเชื้อ 6621601077 หมู่ 700 · ข้อมูลจาก Air4Thai, Open-Meteo, aqicn.org")


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
    theme.sidebar_group("ตัวกรอง")
    provinces = sorted(df["province"].unique())
    sel_prov = st.multiselect("จังหวัด", provinces, placeholder="ทั้งหมด")
    srcs = sorted(df["source"].unique())
    theme.sidebar_group("แหล่งข้อมูล")
    sel_src = [s for s in srcs if st.checkbox(SOURCE_LABEL.get(s, s), value=True, key=f"src_{s}")]
    tmin, tmax = df["observed_at"].min().date(), df["observed_at"].max().date()
    date_range = st.date_input("ช่วงวันที่", value=(max(tmin, tmax - timedelta(days=2)), tmax),
                               min_value=tmin, max_value=tmax)
    pm_max = float(max(df["pm25"].max() or 0, 1))
    pm_range = st.slider("ช่วงค่า PM2.5 (µg/m³)", 0.0, float(round(pm_max + 1)), (0.0, float(round(pm_max + 1))))
    include_null = st.checkbox("รวมแถวที่ไม่มีค่า PM2.5", value=False)
    if st.button("โหลดข้อมูลใหม่"):
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
cards = [theme.kpi_card("จำนวนแถว", f"{len(f):,}", foot=f"ทั้งตาราง {len(df):,} แถว")]
if not valid.empty:
    avg = valid["pm25"].mean()
    lv = theme.aqi_level(avg)
    cards.append(theme.kpi_card("PM2.5 เฉลี่ย", f"{avg:.1f}", unit="µg/m³",
                                tag=(lv["label"], lv["color"], lv["fg"]), foot="ค่าเฉลี่ยทุกแถวที่กรอง"))
    top = valid.loc[valid["pm25"].idxmax()]
    lv = theme.aqi_level(top["pm25"])
    cards.append(theme.kpi_card(
        "PM2.5 สูงสุด", f"{top['pm25']:.1f}", unit="µg/m³",
        tag=("สูงสุดในช่วงที่เลือก", lv["color"], lv["fg"]),
        foot=f"{top['station_name']} ({top['province']}) · {top['observed_at']:%d/%m %H:%M}"))
else:
    cards.append(theme.kpi_card("PM2.5 เฉลี่ย", "-"))
    cards.append(theme.kpi_card("PM2.5 สูงสุด", "-", tag=("สูงสุดในช่วงที่เลือก", "#e2e8f0", "#334155")))
cards.append(theme.kpi_card("จำนวนสถานี", f"{f['station_id'].nunique():,}",
                            foot=f"{f['province'].nunique():,} จังหวัด"))
latest_ts = f["observed_at"].max() if not f.empty else None
cards.append(theme.kpi_card("เวลาข้อมูลล่าสุด", f"{latest_ts:%d/%m %H:%M}" if latest_ts is not None else "-",
                            foot=f"{latest_ts:%Y} · เวลาไทย (UTC+7)" if latest_ts is not None else ""))
theme.kpi_row(cards)
theme.aqi_legend()

if f.empty:
    st.warning("ไม่มีข้อมูลตามตัวกรอง")
    st.stop()

# latest reading per station; prefer measured sources (Air4Thai) over model/scrape when picking "latest"
latest = (valid.assign(_prio=valid["source"].map(SOURCE_PRIORITY).fillna(9))
          .sort_values(["_prio", "observed_at"], ascending=[True, False])
          .drop_duplicates("station_id").drop(columns="_prio"))
latest["ระดับ AQI"] = latest["pm25"].map(lambda v: theme.aqi_level(v)["label"])
latest["แหล่ง"] = latest["source"].map(lambda s: SOURCE_LABEL.get(s, s))

# ---------------------------------------------------------------- charts
left, right = st.columns([3, 2], gap="large")
with left:
    theme.section("แนวโน้ม PM2.5 เฉลี่ยรายชั่วโมง", "แยกตามแหล่งข้อมูล")
    trend = (valid.groupby([pd.Grouper(key="observed_at", freq="h"), "source"])["pm25"].mean()
             .reset_index())
    trend["source"] = trend["source"].map(lambda s: SOURCE_LABEL.get(s, s))
    fig = px.line(trend, x="observed_at", y="pm25", color="source", markers=True,
                  color_discrete_map=SOURCE_COLOR,
                  labels={"observed_at": "เวลา (Asia/Bangkok)", "pm25": "PM2.5 (µg/m³)", "source": "แหล่ง"})
    fig.update_traces(line_width=2.4, marker_size=5)
    theme.add_aqi_bands(fig, trend["pm25"].max() if not trend.empty else 40)
    fig.add_hline(y=37.5, line_dash="dot", line_color="#FFA200",
                  annotation_text="มาตรฐานไทย 37.5 µg/m³ (เฉลี่ย 24 ชม.)", annotation_position="top left")
    st.plotly_chart(theme.style_fig(fig, 420), use_container_width=True)
with right:
    theme.section("Top 10 สถานีที่ฝุ่นสูงสุด", "ค่าล่าสุดของแต่ละสถานี")
    top10 = latest.nlargest(10, "pm25").sort_values("pm25")
    top10["label"] = top10["station_name"].str.slice(0, 28)
    top10.loc[top10["label"].duplicated(keep=False), "label"] += " · " + top10["station_id"]
    fig = px.bar(top10, x="pm25", y="label", orientation="h", color="ระดับ AQI",
                 color_discrete_map=AQI_COLOR_MAP, category_orders={"ระดับ AQI": AQI_ORDER},
                 text="pm25", hover_data={"label": False, "station_name": True, "province": True, "observed_at": True, "แหล่ง": True},
                 labels={"pm25": "PM2.5 (µg/m³)", "label": ""})
    fig.update_traces(texttemplate="%{x:.1f}", textposition="outside", cliponaxis=False,
                      marker_line_width=0, width=0.68)
    fig.update_layout(xaxis_range=[0, max(top10["pm25"].max() * 1.25, 10)], bargap=0.25, xaxis_nticks=5,
                      yaxis={"categoryorder": "array", "categoryarray": top10["label"].tolist()})
    theme.style_fig(fig, 420)
    fig.update_layout(legend=dict(y=-0.18, yanchor="top"), margin=dict(r=30))
    st.plotly_chart(fig, use_container_width=True)

theme.section("แผนที่สถานี", "ค่าล่าสุดของแต่ละสถานี · สีตามระดับ AQI ไทย")
geo = latest.dropna(subset=["lat", "lon"])
fig = px.scatter_mapbox(geo, lat="lat", lon="lon", color="ระดับ AQI", color_discrete_map=AQI_COLOR_MAP,
                        category_orders={"ระดับ AQI": AQI_ORDER}, size=geo["pm25"].clip(lower=5), size_max=17,
                        hover_name="station_name",
                        hover_data={"province": True, "pm25": ":.1f", "observed_at": True, "แหล่ง": True,
                                    "lat": False, "lon": False, "ระดับ AQI": False},
                        zoom=4.7, center={"lat": 13.2, "lon": 101.0}, height=620)
fig.update_traces(marker_opacity=0.88)
theme.style_fig(fig)
fig.update_layout(mapbox_style=theme.MAP_STYLE, margin=dict(l=0, r=0, t=0, b=0),
                  legend=dict(orientation="h", y=0.01, x=0.01, yanchor="bottom",
                              bgcolor="rgba(255,255,255,0.85)"))
st.plotly_chart(fig, use_container_width=True)

theme.section("ตารางข้อมูล", f"{len(f):,} แถวตามตัวกรอง")
show = f.sort_values(["observed_at", "pm25"], ascending=[False, False]).copy()
show["source"] = show["source"].map(lambda s: SOURCE_LABEL.get(s, s))
pm_cap = float(max(show["pm25"].max() or 0, 75))
st.dataframe(show, use_container_width=True, hide_index=True, height=440,
             column_config={
                 "observed_at": st.column_config.DatetimeColumn("observed_at", format="YYYY-MM-DD HH:mm"),
                 "ingested_at": st.column_config.DatetimeColumn("ingested_at", format="YYYY-MM-DD HH:mm"),
                 "pm25": st.column_config.ProgressColumn("pm25 (µg/m³)", format="%.1f", min_value=0, max_value=pm_cap),
             })
st.download_button("ดาวน์โหลด CSV", show.to_csv(index=False).encode("utf-8-sig"), "pm25_filtered.csv", "text/csv")
st.markdown('<div class="aq-foot">ข้อมูลจาก Air4Thai (กรมควบคุมมลพิษ), Open-Meteo Air Quality (CAMS) และ aqicn.org · '
            'เกณฑ์สี: ดัชนีคุณภาพอากาศของประเทศไทย</div>', unsafe_allow_html=True)
