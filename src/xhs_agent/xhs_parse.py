from __future__ import annotations

import hashlib
import re
from datetime import datetime, time as datetime_time, timedelta
from zoneinfo import ZoneInfo


def clean_title(title: str) -> str:
    title = re.sub(r"\s*-\s*小红书.*$", "", title).strip()
    return title[:120]


def clean_body(body: str) -> str:
    lines = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        if line in {"首页", "发现", "消息", "我", "登录", "打开看看"}:
            continue
        lines.append(line)
    return "\n".join(lines)


def title_from_body(body: str) -> str:
    for line in body.splitlines():
        line = line.strip()
        if 4 <= len(line) <= 80 and not re.search(r"^(赞|收藏|评论|分享|关注)$", line):
            return line
    return ""


def looks_login_or_blocked(body: str) -> bool:
    if not body:
        return True
    signals = ("登录后查看更多", "扫码登录", "验证码登录", "请完成验证")
    return any(signal in body for signal in signals) and len(body) < 500


def extract_metric(body: str, labels: tuple[str, ...]) -> int:
    for label in labels:
        patterns = [
            rf"{label}\s*([0-9]+(?:\.[0-9]+)?)\s*([万wWkK]?)",
            rf"([0-9]+(?:\.[0-9]+)?)\s*([万wWkK]?)\s*{label}",
        ]
        for pattern in patterns:
            match = re.search(pattern, body)
            if match:
                return parse_number(match.group(1), match.group(2))
    return 0


def parse_number(value: str, unit: str) -> int:
    number = float(value)
    if unit in {"万", "w", "W"}:
        number *= 10000
    elif unit in {"k", "K"}:
        number *= 1000
    return int(number)


def extract_published_at(body: str) -> datetime | None:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        if match := re.search(r"(今天|昨天)\s+(\d{1,2}):(\d{2})", line):
            day = now.date() if match.group(1) == "今天" else (now - timedelta(days=1)).date()
            return datetime.combine(
                day,
                datetime_time(int(match.group(2)), int(match.group(3))),
                tzinfo=ZoneInfo("Asia/Shanghai"),
            )
        if match := re.search(r"(\d+)\s*天前", line):
            day = (now - timedelta(days=int(match.group(1)))).date()
            return datetime.combine(day, datetime_time(0, 0), tzinfo=ZoneInfo("Asia/Shanghai"))
        if match := re.search(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?", line):
            return _published_datetime(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
                match.group(4),
                match.group(5),
            )
        if match := re.search(r"(\d{1,2})\s*(?:月|[./-])\s*(\d{1,2})\s*(?:日)?\s+(\d{1,2}):(\d{2})", line):
            return _published_datetime(now.year, int(match.group(1)), int(match.group(2)), match.group(3), match.group(4))
    return None


def note_id_from_url(url: str) -> str:
    match = re.search(r"/(?:explore|discovery/item|search_result)/([0-9a-fA-F]+)", url)
    if match:
        return match.group(1)
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def _published_datetime(year: int, month: int, day: int, hour: str | None, minute: str | None) -> datetime:
    return datetime(
        year,
        month,
        day,
        int(hour or 0),
        int(minute or 0),
        tzinfo=ZoneInfo("Asia/Shanghai"),
    )
