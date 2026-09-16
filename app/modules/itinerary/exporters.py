"""行程导出：iCalendar(.ics) / Markdown / 打印友好 HTML。

为什么手写 iCalendar 而不引入 icalendar 库：
    本项目需要的只是 VEVENT 的一个子集（全天与定时事件、纯文本描述），
    手写约 40 行即可覆盖，且避免为一个小功能增加依赖。
    换来的代价是需要自己处理 RFC 5545 的两条硬性要求——见下方 _fold 与 _escape，
    这两处若不遵守，Google Calendar / Apple Calendar 会拒绝导入。

时区处理：
    行程里的 date 是「当地日期」字符串，activity 只有 time_slot 这样的模糊时段。
    因此生成的是**浮动时间**事件（DTSTART 不带 TZID/Z），表示"当地时间"，
    这正是旅行场景想要的语义：用户飞到当地后按当地时间执行。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.modules.itinerary.schemas import ItineraryPlan

# 时段 → 起始小时（浮动当地时间）。行程只给到时段粒度，故取各时段的典型起点。
_TIME_SLOT_START_HOUR = {"morning": 9, "afternoon": 14, "evening": 18}

# 若无具体日期，从一个占位基准日推演（导出时用户可自行改期）
_PLACEHOLDER_BASE_DATE = date(2026, 1, 1)


def _escape(text: str) -> str:
    """RFC 5545 文本转义：反斜杠、分号、逗号、换行都有特殊含义。"""
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _fold(line: str) -> str:
    """RFC 5545 折行：单行不得超过 75 字节，超出部分以 CRLF + 空格续行。

    注意必须按**字节**而非字符切分，否则中文内容会导致行超长被日历应用拒绝。
    """
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line

    chunks: list[bytes] = []
    start = 0
    limit = 75
    while start < len(encoded):
        end = min(start + limit, len(encoded))
        # 避免把多字节字符从中间切断
        while end < len(encoded) and (encoded[end] & 0xC0) == 0x80:
            end -= 1
        chunks.append(encoded[start:end])
        start = end
        limit = 74   # 续行首部有一个空格，占 1 字节
    return "\r\n ".join(chunk.decode("utf-8") for chunk in chunks)


def _stamp(dt: datetime | None = None) -> str:
    """UTC 时间戳格式：YYYYMMDDTHHMMSSZ。

    用 timezone-aware 的 now(timezone.utc)：datetime.utcnow() 已废弃，
    且返回 naive 对象，容易在别处与 aware 时间比较时报错。
    """
    dt = dt or datetime.now(timezone.utc)
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _resolve_day_date(plan: ItineraryPlan, day_index: int) -> date:
    """取某天的日期：优先用攻略中给出的日期，否则基准日顺延。

    这里只需要「哪一天」，不需要时刻，故刻意用 naive datetime 解析后立刻取
    .date()——结果中不含时区信息，不会外泄到后续计算里。
    """
    day_plan = plan.daily_plans[day_index]
    if day_plan.date:
        try:
            return datetime.strptime(day_plan.date, "%Y-%m-%d").date()  # noqa: DTZ007
        except ValueError:
            pass   # 日期格式异常时退回占位基准
    return _PLACEHOLDER_BASE_DATE + timedelta(days=day_index)


def build_ics(plan: ItineraryPlan, *, itinerary_id: int, share_url: str | None = None) -> str:
    """把行程渲染成 iCalendar 文本。

    每天的活动各生成一个 VEVENT；活动按 time_slot 落到典型起始时间，
    时长取 duration_hours。这样导入日历后能直接看到当天的时间安排。
    """
    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Voyage//Itinerary Export//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(plan.destination)}行程",
    ]
    if share_url:
        lines.append(f"X-WR-CALDESC:{_escape('由 Voyage 生成 · ' + share_url)}")

    now = _stamp()
    for day_index, day_plan in enumerate(plan.daily_plans):
        day_date = _resolve_day_date(plan, day_index)
        day_title = f"第{day_plan.day_no}天 · {day_plan.theme}"
        for act_index, act in enumerate(day_plan.activities):
            start_hour = _TIME_SLOT_START_HOUR.get(act.time_slot, 9)
            start_dt = datetime.combine(
                day_date, datetime.min.time()
            ) + timedelta(hours=start_hour)
            end_dt = start_dt + timedelta(hours=max(float(act.duration_hours or 2.0), 0.5))

            description_parts = [act.description]
            if act.cost:
                description_parts.append(f"预估花费：{act.cost} 元")
            if act.note:
                description_parts.append(f"提示：{act.note}")
            description_parts.append(f"（{day_title}）")

            lines.extend([
                "BEGIN:VEVENT",
                f"UID:voyage-itinerary-{itinerary_id}-d{day_plan.day_no}-a{act_index}@voyage",
                f"DTSTAMP:{now}",
                f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}",
                f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}",
                f"SUMMARY:{_escape(act.name)}",
                f"DESCRIPTION:{_escape(' / '.join(p for p in description_parts if p))}",
                f"CATEGORIES:{_escape(act.kind)}",
            ])
            if day_plan.activities and act is day_plan.activities[0]:
                # 当天第一项活动给出地理位置字段的占位（无坐标时不写 GEO）
                lines.append(f"LOCATION:{_escape(act.name + '，' + plan.destination)}")
            lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    # 折行后再拼接：CRLF 是 RFC 5545 要求的行分隔符
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def build_markdown(plan: ItineraryPlan, *, itinerary_id: int, share_url: str | None = None) -> str:
    """把行程渲染成 Markdown 文本（便于粘贴到笔记/IM）。"""
    out: list[str] = [f"# {plan.destination} · {plan.days} 天行程", ""]

    meta: list[str] = []
    if plan.budget:
        meta.append(f"**预算**：{plan.budget} 元")
    if plan.transport:
        meta.append(f"**交通**：{plan.transport}")
    if plan.preferences:
        meta.append(f"**偏好**：{'、'.join(plan.preferences)}")
    if meta:
        out.extend(meta)
        out.append("")

    if plan.accommodation:
        acc = plan.accommodation
        out.append(f"**住宿**：{acc.name}" + (f" — {acc.description}" if acc.description else ""))
        if acc.note:
            out.append(f"> {acc.note}")
        out.append("")

    out.append("---")
    out.append("")

    for day_plan in plan.daily_plans:
        heading = f"## 第 {day_plan.day_no} 天 · {day_plan.theme}"
        if day_plan.date:
            heading += f"（{day_plan.date}）"
        out.extend([heading, "", f"*{day_plan.summary}*", ""])

        for act in day_plan.activities:
            slot = {"morning": "上午", "afternoon": "下午", "evening": "晚上"}.get(
                act.time_slot, act.time_slot
            )
            cost = f"，约 {act.cost} 元" if act.cost else ""
            out.append(f"- **{slot}｜{act.name}**（{act.duration_hours} 小时{cost}）")
            out.append(f"  - {act.description}")
            if act.note:
                out.append(f"  - ⚠️ {act.note}")
        out.append("")

    if plan.tips:
        out.extend(["---", "", "## 出行提醒", ""])
        out.extend(f"- {tip}" for tip in plan.tips)
        out.append("")

    footer = "由 Voyage 生成"
    if share_url:
        footer += f" · {share_url}"
    out.extend(["---", "", f"*{footer}*"])
    return "\n".join(out)


def build_printable_html(
    plan: ItineraryPlan, *, itinerary_id: int, share_url: str | None = None
) -> str:
    """打印友好 HTML：浏览器 Ctrl+P 即可「另存为 PDF」，无需引入 PDF 库。

    样式全部内联，不依赖外部 CSS/字体，保证离线打开与打印结果一致。
    """
    def esc(text: object) -> str:
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    slot_label = {"morning": "上午", "afternoon": "下午", "evening": "晚上"}
    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN"><head><meta charset="utf-8">',
        f"<title>{esc(plan.destination)}行程</title>",
        "<style>",
        "@page { size: A4; margin: 16mm; }",
        "body { font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;",
        "  color: #1f2937; line-height: 1.7; margin: 0; padding: 24px; max-width: 820px; }",
        "h1 { font-size: 26px; margin: 0 0 6px; }",
        ".meta { color: #6b7280; font-size: 14px; margin-bottom: 18px; }",
        ".meta span { margin-right: 16px; }",
        ".day { margin-top: 22px; page-break-inside: avoid; }",
        ".day h2 { font-size: 18px; margin: 0 0 4px; padding-bottom: 6px;",
        "  border-bottom: 2px solid #e5e7eb; }",
        ".summary { color: #6b7280; font-size: 13px; margin: 6px 0 10px; }",
        ".act { display: flex; gap: 10px; padding: 7px 0; border-bottom: 1px dashed #f3f4f6; }",
        ".slot { flex: 0 0 46px; color: #2563eb; font-size: 13px; font-weight: 600; }",
        ".body { flex: 1; }",
        ".name { font-weight: 600; }",
        ".cost { color: #b45309; font-size: 12px; margin-left: 8px; }",
        ".desc { color: #4b5563; font-size: 13px; }",
        ".note { color: #b91c1c; font-size: 12px; }",
        ".tips { margin-top: 24px; padding: 14px 18px; background: #f9fafb;",
        "  border-left: 3px solid #2563eb; font-size: 13px; }",
        ".foot { margin-top: 26px; color: #9ca3af; font-size: 12px; text-align: center; }",
        "</style></head><body>",
        f"<h1>{esc(plan.destination)} · {plan.days} 天行程</h1>",
        '<div class="meta">',
    ]
    if plan.budget:
        parts.append(f"<span>预算 {esc(plan.budget)} 元</span>")
    if plan.transport:
        parts.append(f"<span>交通：{esc(plan.transport)}</span>")
    if plan.preferences:
        parts.append(f"<span>偏好：{esc('、'.join(plan.preferences))}</span>")
    parts.append("</div>")

    if plan.accommodation:
        acc = plan.accommodation
        parts.append(
            f'<div class="desc">住宿：<strong>{esc(acc.name)}</strong>'
            f"{' — ' + esc(acc.description) if acc.description else ''}</div>"
        )

    for day_plan in plan.daily_plans:
        date_suffix = f"（{esc(day_plan.date)}）" if day_plan.date else ""
        parts.append('<div class="day">')
        parts.append(
            f"<h2>第 {day_plan.day_no} 天 · {esc(day_plan.theme)}{date_suffix}</h2>"
        )
        parts.append(f'<div class="summary">{esc(day_plan.summary)}</div>')
        for act in day_plan.activities:
            parts.append('<div class="act">')
            parts.append(
                f'<div class="slot">{esc(slot_label.get(act.time_slot, act.time_slot))}</div>'
            )
            parts.append('<div class="body">')
            cost = f'<span class="cost">约 {esc(act.cost)} 元</span>' if act.cost else ""
            parts.append(
                f'<div><span class="name">{esc(act.name)}</span>'
                f'<span class="cost">{esc(act.duration_hours)} 小时</span>{cost}</div>'
            )
            parts.append(f'<div class="desc">{esc(act.description)}</div>')
            if act.note:
                parts.append(f'<div class="note">⚠️ {esc(act.note)}</div>')
            parts.append("</div></div>")
        parts.append("</div>")

    if plan.tips:
        parts.append('<div class="tips"><strong>出行提醒</strong><ul>')
        parts.extend(f"<li>{esc(tip)}</li>" for tip in plan.tips)
        parts.append("</ul></div>")

    footer = f"由 Voyage 生成 · 行程 #{itinerary_id}"
    if share_url:
        footer += f" · {esc(share_url)}"
    parts.append(f'<div class="foot">{footer}</div>')
    parts.append("</body></html>")
    return "\n".join(parts)
