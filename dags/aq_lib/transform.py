"""Normalise every source into one schema, then de-duplicate across sources."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from aq_lib.db import SOURCE_PRIORITY

BKK = ZoneInfo("Asia/Bangkok")
PM25_MIN, PM25_MAX = 0.0, 1000.0
THAI_BBOX = (5.5, 20.6, 97.3, 105.7)  # lat_min, lat_max, lon_min, lon_max

PROVINCE_ALIASES = {
    "bangkok": "Bangkok", "krung thep maha nakhon": "Bangkok", "bkk": "Bangkok",
    "ayutthaya": "Phra Nakhon Si Ayutthaya", "korat": "Nakhon Ratchasima",
    "chonburi": "Chon Buri", "nonthaburi province": "Nonthaburi",
    "pattanee": "Pattani", "suphun buri": "Suphan Buri",
    "mueang ang thong district ang thong": "Ang Thong",
}

# US EPA PM2.5 breakpoints: (AQI low, AQI high, conc low, conc high)
AQI_BREAKPOINTS = [
    (0, 50, 0.0, 12.0), (51, 100, 12.1, 35.4), (101, 150, 35.5, 55.4),
    (151, 200, 55.5, 150.4), (201, 300, 150.5, 250.4), (301, 500, 250.5, 500.4),
]


def to_float(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # NaN -> None


def clean_pm25(v):
    f = to_float(v)
    if f is None or f < PM25_MIN or f > PM25_MAX:
        return None  # Air4Thai uses -1 for "no data"
    return round(f, 1)


def norm_text(s):
    if s is None:
        return None
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s or None


def norm_province(p):
    p = norm_text(p)
    if not p:
        return None
    p = re.sub(r"(?i)\bprovince\b", "", p.replace("-", " ").replace("_", " ")).strip(" .")
    return PROVINCE_ALIASES.get(p.lower(), p.title())


def floor_hour(dt):
    return dt.astimezone(BKK).replace(minute=0, second=0, microsecond=0)


def aqi_to_pm25(aqi):
    a = to_float(aqi)
    if a is None or a < 0:
        return None
    for il, ih, cl, ch in AQI_BREAKPOINTS:
        if a <= ih:
            return round((a - il) * (ch - cl) / (ih - il) + cl, 1)
    return None


def _record(station_id, name, province, lat, lon, pm25, observed_at, source):
    return {
        "station_id": norm_text(station_id),
        "station_name": norm_text(name),
        "province": norm_province(province),
        "lat": to_float(lat),
        "lon": to_float(lon),
        "pm25": pm25,
        "observed_at": observed_at.isoformat(),
        "source": source,
    }


def normalize_air4thai(stations):
    out = []
    for s in stations:
        last = s.get("AQILast") or {}
        try:
            obs = datetime.strptime(f"{last['date']} {last['time']}", "%Y-%m-%d %H:%M").replace(tzinfo=BKK)
        except (KeyError, ValueError):
            continue
        out.append(_record(
            s.get("stationID"), s.get("nameEN") or s.get("nameTH"),
            (s.get("areaEN") or "").split(",")[-1], s.get("lat"), s.get("long"),
            clean_pm25((last.get("PM25") or {}).get("value")), floor_hour(obs), "air4thai",
        ))
    return out


def normalize_openmeteo(records, now=None):
    now = now or datetime.now(BKK)
    out = []
    for r in records:
        try:
            obs = datetime.strptime(r["time_local"], "%Y-%m-%dT%H:%M").replace(tzinfo=BKK)
        except (KeyError, ValueError):
            continue
        if obs > now:  # skip forecast hours, keep observations/analysis only
            continue
        out.append(_record(r["station_id"], r["station_name"], r["province"], r["lat"], r["lon"],
                           clean_pm25(r.get("pm25")), floor_hour(obs), "openmeteo"))
    return out


def normalize_aqicn(records):
    out = []
    for r in records:
        if not r.get("time_local"):
            continue
        try:
            obs = datetime.strptime(f"{r['time_local']} {r.get('tz') or '+07:00'}", "%Y-%m-%d %H:%M:%S %z")
        except ValueError:
            continue
        out.append(_record(f"aqicn_{r['aqicn_id']}", r.get("station_name"), r.get("province_slug"),
                           r.get("lat"), r.get("lon"), clean_pm25(aqi_to_pm25(r.get("aqi_pm25"))),
                           floor_hour(obs), "aqicn_scrape"))
    return out


def dedupe_key(r):
    if r["lat"] is not None and r["lon"] is not None:
        loc = (round(r["lat"], 3), round(r["lon"], 3))
    else:
        loc = ((r["station_name"] or "").lower(),)
    return loc + (r["observed_at"],)


def dedupe(records):
    """Keep one row per (location, hour) and per (station_id, hour), preferring higher-priority sources.

    Returns (kept_records, removed_count, removed_by_source)."""
    ordered = sorted(records, key=lambda r: SOURCE_PRIORITY.get(r["source"], 99))
    seen_loc, seen_pk, kept, removed = set(), set(), [], {}
    for r in ordered:
        k1, k2 = dedupe_key(r), (r["station_id"], r["observed_at"])
        if not r["station_id"] or k1 in seen_loc or k2 in seen_pk:
            removed[r["source"]] = removed.get(r["source"], 0) + 1
            continue
        seen_loc.add(k1)
        seen_pk.add(k2)
        kept.append(r)
    return kept, sum(removed.values()), removed


def in_thailand(r):
    lat_min, lat_max, lon_min, lon_max = THAI_BBOX
    return (r["lat"] is not None and r["lon"] is not None
            and lat_min <= r["lat"] <= lat_max and lon_min <= r["lon"] <= lon_max)
