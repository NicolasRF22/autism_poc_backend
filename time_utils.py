from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    BRASILIA_TZ = ZoneInfo('America/Sao_Paulo')
except Exception:
    BRASILIA_TZ = timezone(timedelta(hours=-3))


def now_brasilia() -> datetime:
    return datetime.now(BRASILIA_TZ)


def now_brasilia_iso() -> str:
    return now_brasilia().isoformat()


def now_brasilia_filename() -> str:
    return now_brasilia().strftime('%Y%m%d_%H%M%S')