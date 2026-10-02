"""时间展示工具：数据库统一存 UTC，对外展示统一转配置时区（默认东八区）。"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.config import config

# 展示时区来自配置，而不是写死 Asia/Shanghai。
# 写死会导致：改 APP_TIMEZONE 后，AI 侧（date_context / usage_query）已按新时区，
# 而展示侧仍按东八区，同一条数据出现两种时间口径。
LOCAL_TZ = ZoneInfo(config.APP_TIMEZONE)


def to_local_display(dt: datetime) -> str:
    """把（UTC）时间转为上海时区展示字符串，如 "2026-08-26 16:55:03"。

    SQLite 不含时区信息，ORM 读回的是 naive datetime；
    这里显式按 UTC 处理，避免 astimezone 误按服务器本地时区假设而偏 8 小时。
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")