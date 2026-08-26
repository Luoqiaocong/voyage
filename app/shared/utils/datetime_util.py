"""时间展示工具：数据库统一存 UTC，对外展示统一转上海时区（东八区）。"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Asia/Shanghai")


def to_local_display(dt: datetime) -> str:
    """把（UTC）时间转为上海时区展示字符串，如 "2026-08-26 16:55:03"。

    SQLite 不含时区信息，ORM 读回的是 naive datetime；
    这里显式按 UTC 处理，避免 astimezone 误按服务器本地时区假设而偏 8 小时。
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")