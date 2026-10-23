"""Design tokens + the single CSS function + small render helpers shared by every page.

Colour rule: one accent (ACCENT). Saturated colours are reserved for Thai AQI levels and pipeline status.
"""
import html

import streamlit as st
from PIL import Image, ImageDraw

# ---------------------------------------------------------------- tokens
ACCENT = "#1e40af"
BG = "#f8fafc"
SURFACE = "#ffffff"
BORDER = "#e2e8f0"
GRID = "#eef2f6"
TEXT = "#0f172a"
TEXT_2 = "#475569"
MUTED = "#94a3b8"
SIDEBAR_BG = "#0f172a"
SIDEBAR_TEXT = "#e2e8f0"
SIDEBAR_MUTED = "#94a3b8"
SIDEBAR_FIELD = "#1e293b"
RADIUS = 6
SPACE = 8  # spacing unit (px)

FONT_STACK = ("'Sarabun', 'Noto Sans Thai', 'IBM Plex Sans Thai', 'Leelawadee UI', 'Thonburi', "
              "system-ui, -apple-system, 'Segoe UI', sans-serif")
PLOT_FONT = FONT_STACK.replace("'", "")

# Thai PM2.5 AQI bands (Pollution Control Department, µg/m³): upper bound, Thai label, colour, text on colour
AQI_LEVELS = [
    (15.0, "ดีมาก", "#3BCCFF", "#06364a"),
    (25.0, "ดี", "#92D050", "#1f3a07"),
    (37.5, "ปานกลาง", "#FFD60A", "#3d3300"),
    (75.0, "เริ่มมีผลกระทบ", "#FFA200", "#3d2700"),
    (float("inf"), "มีผลกระทบ", "#F04646", "#ffffff"),
]
AQI_ORDER = [lvl[1] for lvl in AQI_LEVELS]
AQI_COLOR_MAP = {lvl[1]: lvl[2] for lvl in AQI_LEVELS}
THAI_STANDARD = 37.5

# one fixed colour per source, used by every chart (accent family + neutrals, not AQI colours)
SOURCE_LABEL = {"air4thai": "Air4Thai", "openmeteo": "Open-Meteo", "aqicn_scrape": "aqicn.org"}
SOURCE_COLOR = {"Air4Thai": ACCENT, "Open-Meteo": "#64748b", "aqicn.org": "#7dd3fc"}
SOURCE_PRIORITY = {"air4thai": 1, "openmeteo": 2, "aqicn_scrape": 3}

STATUS_COLOR = {"success": "#16a34a", "partial": "#ca8a04", "quarantined": "#ea580c",
                "failed": "#dc2626", "skipped": "#94a3b8", "never": "#94a3b8"}
STATUS_LABEL = {"success": "ปกติ", "partial": "บางส่วน", "quarantined": "กักกัน",
                "failed": "ล้มเหลว", "skipped": "ข้าม", "never": "ยังไม่รัน"}

# light basemap without a token: white background + faded OSM raster (falls back to plain white offline).
# carto-positron now returns "API KEY REQUIRED" tiles, so it is not used.
MAP_STYLE = "white-bg"
MAP_LAYERS = [{"below": "traces", "sourcetype": "raster", "opacity": 0.45,
               "sourceattribution": "© OpenStreetMap contributors",
               "source": ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"]}]


def page_icon():
    """Tab icon drawn locally (no emoji, no external file)."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((4, 4, 60, 60), radius=8, fill=ACCENT)
    for y, x2 in ((20, 48), (32, 54), (44, 38)):
        d.rectangle((12, y - 4, x2, y + 4), fill="#ffffff")
    return img


def aqi_level(pm25):
    if pm25 is None or pm25 != pm25:
        return None
    for upper, label, color, fg in AQI_LEVELS:
        if pm25 <= upper:
            return {"label": label, "color": color, "fg": fg}
    return None


# ---------------------------------------------------------------- CSS (the only place styles live)
def inject_css():
    st.markdown(f"""<style>
html, body, .stApp, .stMarkdown, label, input, textarea, button {{ font-family: {FONT_STACK}; }}
[data-testid="stIconMaterial"], .material-symbols-rounded {{ font-family: 'Material Symbols Rounded' !important; }}
.stApp {{ background: {BG}; color: {TEXT}; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding: {SPACE * 4}px {SPACE * 4}px {SPACE * 6}px; max-width: 1440px; }}
[data-testid="stMain"] [data-testid="stVerticalBlock"] {{ gap: {SPACE * 2}px; }}

/* sidebar */
[data-testid="stSidebar"] {{ background: {SIDEBAR_BG}; border-right: 1px solid #1e293b; }}
[data-testid="stSidebar"] p, [data-testid="stSidebar"] label, [data-testid="stSidebar"] span,
[data-testid="stSidebar"] div {{ color: {SIDEBAR_TEXT}; }}
[data-testid="stSidebarNav"] a {{ border-radius: {RADIUS}px; }}
[data-testid="stSidebarNav"] a[aria-current="page"] {{ background: {SIDEBAR_FIELD}; }}
[data-testid="stSidebarNav"] a span {{ color: {SIDEBAR_TEXT} !important; font-size: .9rem; }}
[data-testid="stSidebarNavSeparator"] {{ border-color: #1e293b; }}
[data-testid="stSidebar"] [data-baseweb="select"] > div, [data-testid="stSidebar"] [data-baseweb="input"] > div,
[data-testid="stSidebar"] [data-baseweb="base-input"], [data-testid="stSidebar"] input {{
  background: {SIDEBAR_FIELD} !important; border-color: #334155 !important; border-radius: {RADIUS}px !important;
  color: {SIDEBAR_TEXT} !important; -webkit-text-fill-color: {SIDEBAR_TEXT}; }}
[data-testid="stSidebar"] [data-baseweb="tag"] {{ background: #334155 !important; border-radius: 4px !important; }}
[data-testid="stSidebar"] .stButton > button {{ background: transparent; border: 1px solid #334155;
  border-radius: {RADIUS}px; width: 100%; }}
[data-testid="stSidebar"] .stButton > button:hover {{ border-color: {SIDEBAR_MUTED}; }}
[data-testid="stTickBar"], [data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"] {{ display: none; }}
[data-testid="stSliderThumbValue"] {{ font-family: {FONT_STACK}; font-size: .75rem; font-variant-numeric: tabular-nums; }}
.sb-group {{ font-size: .72rem; font-weight: 600; letter-spacing: .04em;
  color: {SIDEBAR_MUTED} !important; margin: {SPACE * 2}px 0 {SPACE // 2}px; }}

/* header */
.ph {{ display: flex; justify-content: space-between; align-items: flex-end; gap: {SPACE * 2}px;
  padding-bottom: {SPACE * 2}px; border-bottom: 1px solid {BORDER}; flex-wrap: wrap; }}
.ph h1 {{ font-size: 20px; font-weight: 600; margin: 0; padding: 0; color: {TEXT}; line-height: 1.3; }}
.ph .sub {{ font-size: .85rem; color: {TEXT_2}; margin-top: 2px; }}
.ph .live {{ font-size: .8rem; color: {TEXT_2}; white-space: nowrap; font-variant-numeric: tabular-nums; }}
.dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin: 0 4px 0 2px; vertical-align: 1px; }}

/* section title */
.sec {{ display: flex; align-items: baseline; gap: {SPACE}px; margin-top: {SPACE}px; }}
.sec h3 {{ font-size: .95rem; font-weight: 600; margin: 0; padding: 0; color: {TEXT}; }}
.sec span {{ font-size: .75rem; color: {MUTED}; }}

/* cards */
.card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS}px; padding: {SPACE * 2}px;
  min-width: 0; overflow: hidden; box-sizing: border-box; }}
.card.aqi {{ border-left: 3px solid var(--aqi); }}
.lbl {{ font-size: .7rem; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: {TEXT_2}; }}
.val {{ font-size: 1.6rem; font-weight: 600; color: {TEXT}; line-height: 1.2; margin-top: {SPACE // 2}px;
  font-variant-numeric: tabular-nums; white-space: nowrap; }}
.val small {{ font-size: .75rem; font-weight: 400; color: {MUTED}; margin-left: 3px; }}
.cmp {{ font-size: .75rem; color: {TEXT_2}; margin-top: {SPACE // 2}px; font-variant-numeric: tabular-nums;
  line-height: 1.4; }}
.cmp b {{ font-weight: 600; color: {TEXT}; }}
.aqi-tag {{ display: inline-block; font-size: .68rem; font-weight: 600; padding: 0 6px; border-radius: 4px;
  margin-left: 6px; vertical-align: 3px; }}
[data-testid="stPlotlyChart"] {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS}px; padding: {SPACE}px; }}
[data-testid="stDataFrame"] {{ border: 1px solid {BORDER}; border-radius: {RADIUS}px; }}
[data-testid="stExpander"] details {{ border: 1px solid {BORDER}; border-radius: {RADIUS}px; background: {SURFACE}; }}
.legend {{ display: flex; gap: {SPACE * 2}px; flex-wrap: wrap; font-size: .72rem; color: {TEXT_2}; }}
.legend i {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px; vertical-align: -1px; }}
.badge {{ display: inline-flex; align-items: center; font-size: .72rem; font-weight: 600; padding: 1px 8px;
  border-radius: 4px; border: 1px solid {BORDER}; background: {SURFACE}; color: {TEXT_2}; white-space: nowrap; }}
.src-head {{ display: flex; justify-content: space-between; align-items: center; gap: {SPACE}px; }}
.src-head b {{ font-size: .9rem; font-weight: 600; color: {TEXT}; }}
.err {{ margin-top: {SPACE}px; font-size: .72rem; color: #b91c1c; word-break: break-word; }}
.muted {{ font-size: .75rem; color: {MUTED}; }}
</style>""", unsafe_allow_html=True)


# ---------------------------------------------------------------- helpers
def esc(s):
    return html.escape(str(s))


def status_dot(status):
    return f'<span class="dot" style="background:{STATUS_COLOR.get(status, MUTED)}"></span>'


def badge(status, text=None):
    return f'<span class="badge">{status_dot(status)}{esc(text or STATUS_LABEL.get(status, status))}</span>'


def header(title, subtitle, live_html=""):
    st.markdown(f'<div class="ph"><div><h1>{esc(title)}</h1><div class="sub">{esc(subtitle)}</div></div>'
                f'<div class="live">{live_html}</div></div>', unsafe_allow_html=True)


def sidebar_group(title):
    st.markdown(f'<div class="sb-group">{esc(title)}</div>', unsafe_allow_html=True)


def section(title, hint=""):
    st.markdown(f'<div class="sec"><h3>{esc(title)}</h3><span>{esc(hint)}</span></div>', unsafe_allow_html=True)


def kpi(label, value, unit="", cmp_html="", aqi=None, tag=None):
    """One KPI card. `aqi` adds the 3px left level bar; `tag` = (text, bg, fg) small label next to the value."""
    cls = "card aqi" if aqi else "card"
    bar = f"border-left:3px solid {aqi['color']};" if aqi else ""
    style = f' style="height:148px;{bar}"'
    unit_html = f"<small>{esc(unit)}</small>" if unit else ""
    tag_html = (f'<span class="aqi-tag" style="background:{tag[1]};color:{tag[2]}">{esc(tag[0])}</span>'
                if tag else "")
    return (f'<div class="{cls}"{style}><div class="lbl">{esc(label)}</div>'
            f'<div class="val">{value}{unit_html}{tag_html}</div><div class="cmp">{cmp_html}</div></div>')


def aqi_legend():
    st.markdown('<div class="legend">' + "".join(
        f'<span><i style="background:{c}"></i>{label} '
        f'{"≤" + format(u, "g") if u != float("inf") else ">75"}</span>'
        for u, label, c, _ in AQI_LEVELS) + "</div>", unsafe_allow_html=True)


def style_fig(fig, height=None, legend=True):
    fig.update_layout(
        template="plotly_white", paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family=PLOT_FONT, color=TEXT_2, size=12),
        margin=dict(l=8, r=16, t=36 if legend else 8, b=8),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, title_text="",
                    font=dict(size=11)),
        showlegend=legend,
        hoverlabel=dict(font_family=PLOT_FONT, bgcolor=SURFACE, bordercolor=BORDER, font_color=TEXT),
    )
    fig.update_xaxes(gridcolor=GRID, linecolor=BORDER, zeroline=False, tickfont=dict(size=11))
    fig.update_yaxes(gridcolor=GRID, linecolor=BORDER, zeroline=False, tickfont=dict(size=11))
    if height:
        fig.update_layout(height=height)
    return fig


PLOT_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d", "toImage"]}
SPARK_CONFIG = {"displayModeBar": False, "staticPlot": True}
