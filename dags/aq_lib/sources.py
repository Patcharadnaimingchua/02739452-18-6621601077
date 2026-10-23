"""Fetchers for the three data sources. Each returns raw-ish records; normalisation lives in transform.py."""
import os
import re
import tempfile
import time
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import certifi
import requests
from bs4 import BeautifulSoup

USER_AGENT = "KU-02739452-AirQualityExam/1.0 (student 6621601077; educational, non-commercial)"
HEADERS = {"User-Agent": USER_AGENT}
TIMEOUT = 30

# Used by Open-Meteo when Air4Thai (our source of station coordinates) is down.
FALLBACK_STATIONS = [
    {"station_id": "om_bangkok", "station_name": "Bangkok (city centre)", "province": "Bangkok", "lat": 13.7563, "lon": 100.5018},
    {"station_id": "om_chiangmai", "station_name": "Chiang Mai (city)", "province": "Chiang Mai", "lat": 18.7883, "lon": 98.9853},
    {"station_id": "om_chiangrai", "station_name": "Chiang Rai (city)", "province": "Chiang Rai", "lat": 19.9105, "lon": 99.8406},
    {"station_id": "om_lampang", "station_name": "Lampang (city)", "province": "Lampang", "lat": 18.2888, "lon": 99.4908},
    {"station_id": "om_phitsanulok", "station_name": "Phitsanulok (city)", "province": "Phitsanulok", "lat": 16.8211, "lon": 100.2659},
    {"station_id": "om_khonkaen", "station_name": "Khon Kaen (city)", "province": "Khon Kaen", "lat": 16.4419, "lon": 102.8360},
    {"station_id": "om_udonthani", "station_name": "Udon Thani (city)", "province": "Udon Thani", "lat": 17.4138, "lon": 102.7870},
    {"station_id": "om_korat", "station_name": "Nakhon Ratchasima (city)", "province": "Nakhon Ratchasima", "lat": 14.9799, "lon": 102.0978},
    {"station_id": "om_ubon", "station_name": "Ubon Ratchathani (city)", "province": "Ubon Ratchathani", "lat": 15.2287, "lon": 104.8564},
    {"station_id": "om_chonburi", "station_name": "Chon Buri (city)", "province": "Chon Buri", "lat": 13.3611, "lon": 100.9847},
    {"station_id": "om_rayong", "station_name": "Rayong (city)", "province": "Rayong", "lat": 12.6814, "lon": 101.2816},
    {"station_id": "om_ayutthaya", "station_name": "Ayutthaya (city)", "province": "Phra Nakhon Si Ayutthaya", "lat": 14.3532, "lon": 100.5689},
    {"station_id": "om_suratthani", "station_name": "Surat Thani (city)", "province": "Surat Thani", "lat": 9.1382, "lon": 99.3215},
    {"station_id": "om_phuket", "station_name": "Phuket (city)", "province": "Phuket", "lat": 7.8804, "lon": 98.3923},
    {"station_id": "om_hatyai", "station_name": "Hat Yai", "province": "Songkhla", "lat": 7.0084, "lon": 100.4747},
]


CERT_DIR = os.path.join(os.path.dirname(__file__), "certs")
_CA_BUNDLE = None


def ca_bundle():
    """certifi + Let's Encrypt YR1 intermediate/Root YR (cross-signed by ISRG Root X1).

    air4thai.pcd.go.th serves a leaf from LE "YR1" but attaches an unrelated Sectigo chain,
    so the default bundle cannot build the path. We add the missing intermediates; TLS
    verification stays ON."""
    global _CA_BUNDLE
    if _CA_BUNDLE is None or not os.path.exists(_CA_BUNDLE):
        path = os.path.join(tempfile.gettempdir(), "aq_ca_bundle.pem")
        with open(path, "w") as out, open(certifi.where()) as base:
            out.write(base.read())
            for name in sorted(os.listdir(CERT_DIR)):
                with open(os.path.join(CERT_DIR, name)) as extra:
                    out.write("\n" + extra.read())
        _CA_BUNDLE = path
    return _CA_BUNDLE


def _get(url, **kw):
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, verify=ca_bundle(), **kw)
    resp.raise_for_status()
    return resp


# ---------------------------------------------------------------- Source A: Air4Thai JSON API
def fetch_air4thai():
    url = os.environ.get("AIR4THAI_URL", "https://air4thai.pcd.go.th/services/getNewAQI_JSON.php")
    data = _get(url).json()
    stations = data.get("stations") or []
    if not stations:
        raise ValueError("Air4Thai response has no 'stations'")
    return stations


def air4thai_station_list(stations):
    """Station metadata (id/name/province/coords) used to drive the Open-Meteo requests."""
    out = []
    for s in stations:
        try:
            lat, lon = float(s["lat"]), float(s["long"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append({
            "station_id": s.get("stationID"),
            "station_name": s.get("nameEN") or s.get("nameTH"),
            "province": (s.get("areaEN") or "").split(",")[-1],
            "lat": lat,
            "lon": lon,
        })
    return out


# ---------------------------------------------------------------- Source B: Open-Meteo Air Quality API
def region_of(lat, lon):
    if lat >= 17.0:
        return "north"
    if lat < 11.0:
        return "south"
    if lon >= 101.6 and lat >= 14.0:
        return "northeast"
    if lon >= 100.85 and lat < 14.0:
        return "east"
    return "central"


def make_region_batches(stations, max_per_batch=50):
    by_region = {}
    for s in stations:
        by_region.setdefault(region_of(s["lat"], s["lon"]), []).append(s)
    batches = []
    for region, items in sorted(by_region.items()):
        for i in range(0, len(items), max_per_batch):
            part = items[i:i + max_per_batch]
            name = region if len(items) <= max_per_batch else f"{region}-{i // max_per_batch + 1}"
            batches.append({"region": name, "stations": part})
    return batches


def fetch_openmeteo(stations):
    url = os.environ.get("OPENMETEO_URL", "https://air-quality-api.open-meteo.com/v1/air-quality")
    params = {
        "latitude": ",".join(f"{s['lat']:.5f}" for s in stations),
        "longitude": ",".join(f"{s['lon']:.5f}" for s in stations),
        "hourly": "pm2_5",
        "timezone": "Asia/Bangkok",
        "past_days": 1,
        "forecast_days": 1,
    }
    data = _get(url, params=params).json()
    if isinstance(data, dict):
        if data.get("error"):
            raise ValueError(f"Open-Meteo error: {data.get('reason')}")
        data = [data]
    if len(data) != len(stations):
        raise ValueError(f"Open-Meteo returned {len(data)} locations for {len(stations)} requested")
    records = []
    for st, loc in zip(stations, data):
        hourly = loc.get("hourly") or {}
        for t, v in zip(hourly.get("time", []), hourly.get("pm2_5", [])):
            records.append({**st, "time_local": t, "pm25": v})
    return records


# ---------------------------------------------------------------- Source C: aqicn.org HTML scraping
def _robots_for(base):
    rp = robotparser.RobotFileParser()
    rp.set_url(urljoin(base, "/robots.txt"))
    try:
        resp = requests.get(rp.url, headers=HEADERS, timeout=TIMEOUT, verify=ca_bundle())
        rp.parse(resp.text.splitlines() if resp.status_code == 200 else [])
    except requests.RequestException:
        rp.parse([])
    return rp


def _aqicn_page(html, url):
    soup = BeautifulSoup(html, "lxml")
    cur = soup.find(id="cur_pm25")
    title = soup.find(id="aqiwgttitle1")
    if cur is None or title is None:
        return None
    m_time = re.search(r'"utc":\{"v":\d+,"tz":"([+-]\d{2}:\d{2})","s":"([\d\- :]+)"\}', html)
    m_geo = re.search(r'"geo":\["?([\d.\-]+)"?,"?([\d.\-]+)"?\]', html)
    path = [p for p in urlparse(url).path.split("/") if p]
    # /city/thailand/<province>/<station>/  -> province slug
    province = path[2] if len(path) >= 4 and path[1] == "thailand" else (path[1] if len(path) >= 2 else None)
    name = re.sub(r"\s*AQI\s*$", "", title.get_text(" ", strip=True))
    return {
        "aqicn_url": url,
        "station_name": name,
        "province_slug": province,
        "aqi_pm25": cur.get_text(strip=True),
        "time_local": m_time.group(2) if m_time else None,
        "tz": m_time.group(1) if m_time else None,
        "lat": m_geo.group(1) if m_geo else None,
        "lon": m_geo.group(2) if m_geo else None,
    }


def scrape_aqicn():
    base = os.environ.get("AQICN_BASE_URL", "https://aqicn.org")
    max_pages = int(os.environ.get("SCRAPE_MAX_PAGES", "40"))
    delay = float(os.environ.get("SCRAPE_DELAY_SEC", "1.0"))
    rp = _robots_for(base)

    index_url = urljoin(base, "/country/thailand/")
    if not rp.can_fetch(USER_AGENT, index_url):
        raise PermissionError(f"robots.txt disallows {index_url}")
    soup = BeautifulSoup(_get(index_url).text, "lxml")
    links = sorted({a["href"] for a in soup.find_all("a", href=True) if re.match(r"^/city/@\d+/?$", a["href"])})
    if not links:
        raise ValueError("no station links found on aqicn country page")

    records, errors = [], 0
    for href in links[:max_pages]:
        url = urljoin(base, href)
        if not rp.can_fetch(USER_AGENT, url):
            continue
        time.sleep(delay)  # be polite: one request per `delay` seconds
        try:
            resp = _get(url)
            rec = _aqicn_page(resp.text, resp.url)
            if rec:
                rec["aqicn_id"] = href.strip("/").split("@")[-1]
                records.append(rec)
        except requests.RequestException:
            errors += 1
    if not records:
        raise ValueError(f"scraped 0 stations ({errors} request errors)")
    return records
