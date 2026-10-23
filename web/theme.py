"""Shared look & feel: light/dark palette, Thai AQI colours, inline SVG icons, Plotly styling.

Everything is inline (no external images/JS); the web font is optional and falls back to system Thai fonts.
"""
import plotly.io as pio
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
SOURCE_COLOR = {"Air4Thai (API)": "#2563eb", "Open-Meteo (API)": "#0d9488", "aqicn.org (scrape)": "#c026d3"}
SOURCE_PRIORITY = {"air4thai": 1, "openmeteo": 2, "aqicn_scrape": 3}

STATUS_STYLE = {
    "success": ("#16a34a", "#dcfce7", "สำเร็จ"),
    "failed": ("#dc2626", "#fee2e2", "ล้มเหลว"),
    "skipped": ("#64748b", "#e2e8f0", "ข้าม"),
    "quarantined": ("#d97706", "#fef3c7", "กักกัน"),
    "partial": ("#d97706", "#fef3c7", "บางส่วน"),
    "never": ("#64748b", "#e2e8f0", "ยังไม่เคยรัน"),
}

PALETTES = {
    "light": {"bg": "#f5f7fb", "surface": "#ffffff", "surface2": "#eef2f8", "border": "#e2e8f0",
              "text": "#0f172a", "muted": "#64748b", "accent": "#2563eb", "grid": "#e5e9f0",
              "map": "open-street-map", "sidebar": "#ffffff"},
    "dark": {"bg": "#0b1220", "surface": "#131c2e", "surface2": "#1b2640", "border": "#263247",
             "text": "#e5e9f2", "muted": "#94a3b8", "accent": "#60a5fa", "grid": "#223047",
             "map": "open-street-map", "sidebar": "#0f1829"},
}

FONT_STACK = ("'IBM Plex Sans Thai', 'Sarabun', 'Noto Sans Thai', 'Leelawadee UI', 'Thonburi', "
              "'Tahoma', system-ui, -apple-system, 'Segoe UI', sans-serif")

_ICON_PATHS = {
    "logo": '<path d="M3 8h11a3 3 0 1 0-3-3"/><path d="M3 12h15a3 3 0 1 1-3 3"/><path d="M3 16h7"/>',
    "rows": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
    "avg": '<path d="M4 18a8 8 0 1 1 16 0"/><path d="M12 18l4-5"/><circle cx="12" cy="18" r="1.3"/>',
    "max": '<path d="M12 3l3 6 6 .9-4.5 4.3 1 6.3L12 17.6 6.5 20.5l1-6.3L3 9.9 9 9z"/>',
    "station": '<path d="M12 21s-7-6.2-7-11a7 7 0 1 1 14 0c0 4.8-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "trend": '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    "bars": '<path d="M4 6h10"/><path d="M4 12h16"/><path d="M4 18h7"/>',
    "map": '<path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2-6-2z"/><path d="M9 4v14"/><path d="M15 6v14"/>',
    "table": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18"/><path d="M9 10v10"/>',
    "filter": '<path d="M3 5h18l-7 8v6l-4-2v-4z"/>',
    "pipeline": '<circle cx="5" cy="6" r="2"/><circle cx="5" cy="18" r="2"/><circle cx="19" cy="12" r="2"/><path d="M7 6h4a4 4 0 0 1 4 4v0"/><path d="M7 18h4a4 4 0 0 0 4-4v0"/><path d="M15 12h2"/>',
    "check": '<path d="M9 12l2 2 4-4"/><path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/>',
    "history": '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l3 2"/>',
    "log": '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5"/><path d="M9 13h7"/><path d="M9 17h5"/>',
}


def icon(name, size=20, color="currentColor", stroke=2):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" '
            f'fill="none" stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true">{_ICON_PATHS[name]}</svg>')


def page_icon():
    """Browser-tab icon drawn locally (emoji tab icons render as grey boxes on some systems)."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, 62, 62), radius=16, fill="#2563eb")
    for y, x2, c in ((20, 48, "#3BCCFF"), (32, 56, "#92D050"), (44, 40, "#FFD60A")):
        d.rounded_rectangle((10, y - 4, x2, y + 4), radius=4, fill=c)
    return img


def aqi_level(pm25):
    if pm25 is None or pm25 != pm25:
        return None
    for upper, key, label, color, fg in AQI_LEVELS:
        if pm25 <= upper:
            return {"key": key, "label": label, "color": color, "fg": fg}
    return None


def mode():
    return "dark" if st.session_state.get("dark_mode") else "light"


def palette():
    return PALETTES[mode()]


def theme_toggle():
    """Sidebar light/dark switch; the choice lives in session_state."""
    with st.sidebar:
        st.toggle("โหมดมืด (Dark mode)", key="dark_mode")


def inject_css():
    p = palette()
    dark = mode() == "dark"
    st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Thai:wght@400;500;600;700&display=swap');
:root {{
  --bg:{p['bg']}; --surface:{p['surface']}; --surface2:{p['surface2']}; --border:{p['border']};
  --text:{p['text']}; --muted:{p['muted']}; --accent:{p['accent']};
}}
html, body, .stApp, .stMarkdown p, .stMarkdown li, label, input, textarea, .aq-header, .kpi, .src-card, .aq-section
{{ font-family: {FONT_STACK}; }}
/* never override the icon font (otherwise icons show as their ligature text or as grey boxes) */
[data-testid="stIconMaterial"], .material-symbols-rounded {{ font-family: 'Material Symbols Rounded' !important; }}
.stApp {{ background: var(--bg); color: var(--text); }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stSidebar"] {{ background: {p['sidebar']}; border-right: 1px solid var(--border); }}
[data-testid="stSidebar"] p, [data-testid="stSidebar"] label, .stApp p, .stApp label, .stApp span, .stApp h1, .stApp h2, .stApp h3, .stApp li {{ color: var(--text); }}
.block-container {{ padding-top: 2.2rem; max-width: 1400px; }}
{'''
[data-baseweb="select"] > div, [data-baseweb="input"] > div, [data-baseweb="base-input"], .stDateInput input,
[data-testid="stSidebar"] [data-baseweb="select"] > div { background: var(--surface2) !important; border-color: var(--border) !important; }
[data-baseweb="select"] div, [data-baseweb="input"] input, .stDateInput input, input::placeholder { color: var(--text) !important; -webkit-text-fill-color: var(--text) !important; }
[data-baseweb="popover"] ul, [data-baseweb="menu"], [data-baseweb="calendar"] { background: var(--surface) !important; }
[data-baseweb="popover"] li, [data-baseweb="calendar"] * { color: var(--text) !important; }
.stButton > button, .stDownloadButton > button { background: var(--surface2); color: var(--text); border-color: var(--border); }
[data-testid="stDataFrame"] { filter: invert(0.88) hue-rotate(180deg); }
[data-testid="stExpander"] { background: var(--surface); border-color: var(--border); }
''' if dark else ''}
.aq-header {{ display:flex; align-items:center; gap:16px; padding:18px 22px; border-radius:16px;
  background: linear-gradient(120deg, {'#1e3a8a, #0f766e' if dark else '#2563eb, #0ea5e9'}); color:#fff; margin-bottom:18px;
  box-shadow: 0 6px 24px rgba(37,99,235,.18); }}
.aq-header .logo {{ width:52px; height:52px; border-radius:14px; background:rgba(255,255,255,.18);
  display:flex; align-items:center; justify-content:center; flex-shrink:0; }}
.aq-header h1 {{ font-size:1.45rem; line-height:1.3; margin:0; padding:0; color:#fff !important; font-weight:700; }}
.aq-header .sub {{ font-size:.86rem; opacity:.92; margin-top:4px; color:#fff !important; }}
.aq-header .chips {{ margin-top:8px; display:flex; flex-wrap:wrap; gap:6px; }}
.aq-header .chip {{ font-size:.75rem; padding:2px 10px; border-radius:999px; background:rgba(255,255,255,.2); color:#fff !important; }}
.aq-section {{ display:flex; align-items:center; gap:10px; margin:22px 0 10px; }}
.aq-section .ic {{ width:32px; height:32px; border-radius:9px; display:flex; align-items:center; justify-content:center;
  background: var(--surface2); color: var(--accent); flex-shrink:0; }}
.aq-section h3 {{ margin:0; padding:0; font-size:1.08rem; font-weight:650; color:var(--text) !important; }}
.aq-section .hint {{ font-size:.8rem; color:var(--muted) !important; margin-left:4px; }}
.kpi-grid {{ display:grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap:12px; margin: 4px 0 8px; }}
@media (max-width: 1100px) {{ .kpi-grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }} }}
@media (max-width: 700px) {{ .kpi-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
.kpi {{ background:var(--surface); border:1px solid var(--border); border-radius:14px; padding:14px 16px;
  border-top:4px solid var(--kc); box-shadow: 0 1px 3px rgba(15,23,42,.06); min-width:0; }}
.kpi .top {{ display:flex; align-items:center; gap:8px; color:var(--muted) !important; font-size:.82rem; }}
.kpi .top span {{ color:var(--muted) !important; }}
.kpi .ic {{ width:30px; height:30px; border-radius:8px; display:flex; align-items:center; justify-content:center;
  background: color-mix(in srgb, var(--kc) 16%, transparent); color: var(--kc); flex-shrink:0; }}
.kpi .val {{ font-size:clamp(1.15rem, 1.7vw, 1.55rem); font-weight:700; margin-top:8px; color:var(--text) !important; line-height:1.2;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.kpi .val small {{ font-size:.8rem; font-weight:500; color:var(--muted) !important; }}
.kpi .foot {{ font-size:.76rem; color:var(--muted) !important; margin-top:4px; line-height:1.35; }}
.kpi .tag {{ display:inline-block; font-size:.7rem; font-weight:600; padding:1px 8px; border-radius:999px; margin-top:6px; }}
.aqi-legend {{ display:flex; flex-wrap:wrap; gap:6px; margin:2px 0 6px; }}
.aqi-legend span {{ font-size:.75rem; padding:3px 10px; border-radius:999px; font-weight:600; }}
.badge {{ display:inline-flex; align-items:center; gap:6px; font-size:.78rem; font-weight:600; padding:3px 10px;
  border-radius:999px; border:1px solid transparent; white-space:nowrap; flex-shrink:0; }}
.badge::before {{ content:""; width:7px; height:7px; border-radius:50%; background:currentColor; }}
.src-card {{ background:var(--surface); border:1px solid var(--border); border-radius:14px; padding:14px 16px; height:100%; }}
.src-card .name {{ font-weight:650; font-size:1rem; color:var(--text) !important; }}
.src-card .big {{ font-size:1.35rem; font-weight:700; margin:8px 0 2px; color:var(--text) !important; }}
.src-card .meta {{ font-size:.78rem; color:var(--muted) !important; }}
.src-card .err {{ margin-top:8px; font-size:.76rem; padding:6px 8px; border-radius:8px; background:#fee2e2; color:#991b1b !important;
  word-break:break-word; }}
.aq-foot {{ text-align:center; color:var(--muted) !important; font-size:.78rem; margin:28px 0 6px; }}
</style>""", unsafe_allow_html=True)


def header(title, subtitle, chips=(), logo="logo"):
    chips_html = "".join(f'<span class="chip">{c}</span>' for c in chips)
    st.markdown(f"""<div class="aq-header"><div class="logo">{icon(logo, 30, "#ffffff", 2.2)}</div>
<div><h1>{title}</h1><div class="sub">{subtitle}</div><div class="chips">{chips_html}</div></div></div>""",
                unsafe_allow_html=True)


def section(title, icon_name, hint=""):
    hint_html = f'<span class="hint">{hint}</span>' if hint else ""
    st.markdown(f'<div class="aq-section"><div class="ic">{icon(icon_name, 18)}</div><h3>{title}</h3>{hint_html}</div>',
                unsafe_allow_html=True)


def kpi_card(label, value, icon_name, color, unit="", foot="", tag=None):
    unit_html = f" <small>{unit}</small>" if unit else ""
    tag_html = (f'<span class="tag" style="background:{tag[1]};color:{tag[2]} !important">{tag[0]}</span>'
                if tag else "")
    return (f'<div class="kpi" style="--kc:{color}"><div class="top"><div class="ic">{icon(icon_name, 17)}</div>'
            f'<span>{label}</span></div><div class="val" title="{value}">{value}{unit_html}</div>'
            f'{tag_html}<div class="foot">{foot}</div></div>')


def kpi_row(cards):
    st.markdown(f'<div class="kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def aqi_legend():
    st.markdown('<div class="aqi-legend">' + "".join(
        f'<span style="background:{c};color:{fg} !important">{label} '
        f'{"≤ " + format(u, "g") if u != float("inf") else "> 75"}</span>'
        for u, _, label, c, fg in AQI_LEVELS) + "</div>", unsafe_allow_html=True)


def badge(status):
    fg, bg, th = STATUS_STYLE.get(status, STATUS_STYLE["skipped"])
    return f'<span class="badge" style="color:{fg} !important;background:{bg};border-color:{fg}33">{status} · {th}</span>'


def style_fig(fig, height=None):
    p = palette()
    fig.update_layout(
        template="plotly_dark" if mode() == "dark" else "plotly_white",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT_STACK.replace("'", ""), color=p["text"], size=13),
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text="",
                    font=dict(color=p["text"])),
        hoverlabel=dict(font_family=FONT_STACK.replace("'", "")),
    )
    axis = dict(gridcolor=p["grid"], zerolinecolor=p["grid"], color=p["muted"], title_font_color=p["text"])
    fig.update_xaxes(**axis)
    fig.update_yaxes(**axis)
    if height:
        fig.update_layout(height=height)
    return fig


def add_aqi_bands(fig, y_max):
    """Faint Thai AQI colour bands behind a PM2.5 time series."""
    lower = 0.0
    for upper, _, label, color, _ in AQI_LEVELS:
        top = min(upper, max(y_max, 40) * 1.1)
        if lower >= top:
            break
        fig.add_hrect(y0=lower, y1=top, fillcolor=color, opacity=0.10, line_width=0, layer="below")
        lower = upper
    return fig


pio.templates.default = "plotly_white"
