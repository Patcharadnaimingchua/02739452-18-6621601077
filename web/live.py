"""Header 'live' indicator shared by both pages."""
from db import latest_run_status
from theme import status_dot

LIVE_TEXT = {"success": "ทุกแหล่งปกติ", "partial": "บางแหล่งล้มเหลว", "quarantined": "ข้อมูลรอบล่าสุดถูกกักกัน",
             "failed": "ทุกแหล่งล้มเหลว"}


def live_html():
    status, ts = latest_run_status()
    if status is None:
        return f'{status_dot("never")}ยังไม่มีการรัน pipeline'
    return f'อัปเดตล่าสุด {ts:%H:%M} (เวลาไทย) · {status_dot(status)}{LIVE_TEXT[status]}'
