import os
from datetime import datetime, timedelta, timezone

# Facility local time. Default UTC+8 (Philippines). Override with env vars:
#   PICKLEBALL_UTC_OFFSET_HOURS=8
#   PICKLEBALL_TIMEZONE=Asia/Manila  (needs tzdata package on Windows)
_OFFSET_HOURS = int(os.getenv("PICKLEBALL_UTC_OFFSET_HOURS", "8"))


def _facility_tz():
    tz_name = os.getenv("PICKLEBALL_TIMEZONE", "").strip()
    if tz_name:
        try:
            from zoneinfo import ZoneInfo

            return ZoneInfo(tz_name)
        except Exception:
            pass
    return timezone(timedelta(hours=_OFFSET_HOURS))


FACILITY_TZ = _facility_tz()


def facility_now() -> datetime:
    """Naive datetime in the facility's local timezone."""
    return datetime.now(FACILITY_TZ).replace(tzinfo=None)
