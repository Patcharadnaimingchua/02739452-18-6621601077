"""Shared look: one light theme, one accent colour; other colours only for AQI levels and status badges."""
import streamlit as st
from PIL import Image, ImageDraw

# Thai PM2.5 AQI bands (Pollution Control Department, 24-h average µg/m³)
AQI_LEVELS = [
    # upper bound, key, Thai label, colour, text colour on top of the colour
    (15.0, "very_good", "ดีมาก", "#3BCCFF", "#06364a"),
    (25.0, "good", "ดี", "#92D050", "#1f3a07"),
    (37.5, "moderate", "ปานกลาง", "#FFD60A", "#3d3300"),
    (75.0, "sensitive", "เริ่มมีผลกระทบต่อสุขภาพ", "#FFA200", "#3d2700"),
    (float("inf"), "unhealthy", "มีผลกระทบต่อสุขภาพ", "#F04646", "#ffffff"),
]
AQI_ORDER = [lvl[2] for lvl in AQI_LEVELS]
AQI_COLOR_MAP = {lvl[2]: lvl[3] for lvl in AQI_LEVELS}

SOURCE_LABEL = {"air4thai": "Air4Thai (API)", "openmeteo": "Open-Meteo (API)", "aqicn_scrape": "aqicn.org (scrape)"}
SOURCE_COLOR = {"Air4Thai (API)": "#1e3a8a", "Open-Meteo (API)": "#6b7280", "aqicn.org (scrape)": "#93a3c4"}
SOURCE_PRIORITY = {"air4thai": 1, "openmeteo": 2, "aqicn_scrape": 3}

STATUS_STYLE = {
    "success": ("#16a34a", "#dcfce7", "สำเร็จ"),
    "failed": ("#dc2626", "#fee2e2", "ล้มเหลว"),
    "skipped": ("#64748b", "#e2e8f0", "ข้าม"),
    "quarantined": ("#d97706", "#fef3c7", "กักกัน"),
    "partial": ("#d97706", "#fef3c7", "บางส่วน"),
    "never": ("#64748b", "#e2e8f0", "ยังไม่เคยรัน"),
}

ACCENT, TEXT, MUTED, BORDER = "#1e3a8a", "#1f2937", "#6b7280", "#d9dee7"
MAP_STYLE = "open-street-map"

FONT_STACK = ("'IBM Plex Sans Thai', 'Sarabun', 'Noto Sans Thai', 'Leelawadee UI', 'Thonburi', "
              "'Tahoma', system-ui, -apple-system, 'Segoe UI', sans-serif")


def page_icon():
    """Browser-tab icon drawn locally (no emoji, no external file)."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((4, 4, 60, 60), radius=8, fill=ACCENT)
    for y, x2 in ((20, 48), (32, 54), (44, 38)):
        d.rectangle((12, y - 4, x2, y + 4), fill="#ffffff")
    return img


def aqi_level(pm25):
    if pm25 is None or pm25 != pm25:
        return None
    for upper, key, label, color, fg in AQI_LEVELS:
        if pm25 <= upper:
            return {"key": key, "label": label, "color": color, "fg": fg}
    return None


def inject_css():
    st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Thai:wght@400;500;600;700&display=swap');
html, body, .stApp, .stMarkdown p, .stMarkdown li, label, input, textarea, .kpi, .src-card
{{ font-family: {FONT_STACK}; }}
/* keep the icon font intact */
[data-testid="stIconMaterial"], .material-symbols-rounded {{ font-family: 'Material Symbols Rounded' !important; }}
.stApp {{ background: #ffffff; color: {TEXT}; }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stSidebar"] {{ background: #f4f5f7; border-right: 1px solid {BORDER}; }}
.block-container {{ padding-top: 2.5rem; max-width: 1400px; }}
.group-title {{ font-size: .85rem; font-weight: 700; color: {TEXT}; margin: 14px 0 4px; }}
/* slider: hide the min/max tick labels that repeat the thumb values */
[data-testid="stTickBar"], [data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"] {{ display: none; }}
.page-head h1 {{ font-size: 1.5rem; font-weight: 700; margin: 0; padding: 0; color: {TEXT}; }}
.page-head p {{ margin: 4px 0 0; color: {MUTED}; font-size: .92rem; }}
.page-head hr {{ margin: 14px 0 18px; border: 0; border-top: 1px solid {BORDER}; }}
.sec-title {{ font-size: 1.05rem; font-weight: 650; margin: 24px 0 8px; color: {TEXT}; }}
.sec-title span {{ font-size: .8rem; font-weight: 400; color: {MUTED}; margin-left: 8px; }}
.kpi-grid {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin: 4px 0 10px; }}
@media (max-width: 1100px) {{ .kpi-grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }} }}
@media (max-width: 700px) {{ .kpi-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
.kpi {{ border: 1px solid {BORDER}; border-radius: 4px; padding: 12px 14px; background: #fff; min-width: 0; }}
.kpi .lbl {{ color: {MUTED}; font-size: .8rem; }}
.kpi .val {{ font-size: clamp(1.15rem, 1.7vw, 1.5rem); font-weight: 700; margin-top: 4px; color: {ACCENT};
  line-height: 1.25; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.kpi .val small {{ font-size: .78rem; font-weight: 400; color: {MUTED}; }}
.kpi .foot {{ font-size: .75rem; color: {MUTED}; margin-top: 4px; line-height: 1.35; }}
.kpi .tag {{ display: inline-block; font-size: .7rem; font-weight: 600; padding: 1px 8px; border-radius: 3px; margin-top: 4px; }}
.aqi-legend {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 6px; }}
.aqi-legend span {{ font-size: .74rem; padding: 2px 9px; border-radius: 3px; font-weight: 600; }}
.badge {{ display: inline-block; font-size: .76rem; font-weight: 600; padding: 2px 9px; border-radius: 3px;
  border: 1px solid transparent; white-space: nowrap; flex-shrink: 0; }}
.src-card {{ border: 1px solid {BORDER}; border-radius: 4px; padding: 12px 14px; height: 100%; background: #fff; }}
.src-card .name {{ font-weight: 650; color: {TEXT}; }}
.src-card .big {{ font-size: 1.3rem; font-weight: 700; margin: 8px 0 2px; color: {ACCENT}; }}
.src-card .meta {{ font-size: .76rem; color: {MUTED}; }}
.src-card .err {{ margin-top: 8px; font-size: .75rem; padding: 6px 8px; border-radius: 3px; background: #fee2e2;
  color: #991b1b; word-break: break-word; }}
.aq-foot {{ text-align: center; color: {MUTED}; font-size: .76rem; margin: 28px 0 6px; }}
</style>""", unsafe_allow_html=True)


def header(title, subtitle):
    st.markdown(f'<div class="page-head"><h1>{title}</h1><p>{subtitle}</p><hr></div>', unsafe_allow_html=True)


def sidebar_group(title):
    st.markdown(f'<div class="group-title">{title}</div>', unsafe_allow_html=True)


def section(title, hint=""):
    hint_html = f"<span>{hint}</span>" if hint else ""
    st.markdown(f'<div class="sec-title">{title}{hint_html}</div>', unsafe_allow_html=True)


def kpi_card(label, value, unit="", foot="", tag=None):
    unit_html = f" <small>{unit}</small>" if unit else ""
    tag_html = (f'<div><span class="tag" style="background:{tag[1]};color:{tag[2]}">{tag[0]}</span></div>'
                if tag else "")
    return (f'<div class="kpi"><div class="lbl">{label}</div><div class="val" title="{value}">{value}{unit_html}</div>'
            f'{tag_html}<div class="foot">{foot}</div></div>')


def kpi_row(cards):
    st.markdown(f'<div class="kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def aqi_legend():
    st.markdown('<div class="aqi-legend">' + "".join(
        f'<span style="background:{c};color:{fg}">{label} '
        f'{"≤ " + format(u, "g") if u != float("inf") else "> 75"}</span>'
        for u, _, label, c, fg in AQI_LEVELS) + "</div>", unsafe_allow_html=True)


def badge(status):
    fg, bg, th = STATUS_STYLE.get(status, STATUS_STYLE["skipped"])
    return f'<span class="badge" style="color:{fg};background:{bg};border-color:{fg}33">{status} · {th}</span>'


def style_fig(fig, height=None):
    font = FONT_STACK.replace("'", "")
    fig.update_layout(
        template="plotly_white", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=font, color=TEXT, size=13), margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text=""),
        hoverlabel=dict(font_family=font),
    )
    fig.update_xaxes(gridcolor="#e5e7eb", zerolinecolor="#e5e7eb")
    fig.update_yaxes(gridcolor="#e5e7eb", zerolinecolor="#e5e7eb")
    if height:
        fig.update_layout(height=height)
    return fig


def add_aqi_bands(fig, y_max):
    """Faint Thai AQI colour bands behind a PM2.5 time series."""
    lower = 0.0
    for upper, _, _, color, _ in AQI_LEVELS:
        top = min(upper, max(y_max, 40) * 1.1)
        if lower >= top:
            break
        fig.add_hrect(y0=lower, y1=top, fillcolor=color, opacity=0.10, line_width=0, layer="below")
        lower = upper
    return fig
