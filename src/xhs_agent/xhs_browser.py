from __future__ import annotations

import re
import subprocess
import time
from datetime import date, datetime, time as datetime_time, timedelta
from zoneinfo import ZoneInfo

from .models import NoteMetrics
from .repository import Repository


def open_xhs_login_page() -> None:
    _osascript('tell application "Google Chrome" to open location "https://www.xiaohongshu.com/explore"')
    print("已打开小红书。请在 Chrome 里完成登录，然后再运行 xhs-browser-collect。")


def collect_notes_with_chrome(
    repo: Repository,
    wait_seconds: float = 5.0,
    limit: int | None = None,
    refresh_all: bool = False,
    report_date: date | None = None,
) -> int:
    if refresh_all:
        urls = repo.known_note_urls()
    elif report_date:
        urls = _dedupe_urls(repo.urls_for_report_date(report_date) + repo.urls_without_browser_data())
    else:
        urls = repo.urls_without_browser_data()
    if limit:
        urls = urls[:limit]
    notes: list[NoteMetrics] = []
    for index, url in enumerate(urls, start=1):
        print(f"采集 {index}/{len(urls)}：{url}")
        try:
            note = collect_one_note(url, wait_seconds)
            notes.append(note)
            print(f"  标题：{note.title[:50]}")
        except Exception as exc:
            print(f"  跳过：{exc}")
    if notes:
        repo.upsert_note_metrics(notes)
    return len(notes)


def _dedupe_urls(urls: list[str]) -> list[str]:
    return list(dict.fromkeys(urls))


def collect_one_note(url: str, wait_seconds: float = 5.0) -> NoteMetrics:
    _ensure_chrome_ready()
    _osascript(f'tell application "Google Chrome" to open location "{url}"')
    time.sleep(wait_seconds)
    page = _read_active_tab()
    title = _clean_title(page.get("title") or "")
    body = _clean_body(page.get("body") or "")
    final_url = page.get("url") or url
    if _looks_login_or_blocked(body):
        raise RuntimeError("页面需要登录或未加载出笔记内容。请先在 Chrome 里登录小红书并打开任意笔记确认可见。")
    if not title or title in {"小红书", "小红书 - 你的生活指南"}:
        title = _title_from_body(body)
    return NoteMetrics(
        note_id=_note_id_from_url(final_url or url),
        url=url,
        account_id=None,
        title=title or "待抓取标题",
        body=body[:2500] or "页面未读取到正文。",
        published_at=_extract_published_at(body),
        likes=_extract_metric(body, ("赞", "点赞")),
        collects=_extract_metric(body, ("收藏",)),
        comments=_extract_metric(body, ("评论",)),
        shares=_extract_metric(body, ("分享",)),
        views=_extract_metric(body, ("浏览", "阅读")),
        leads=0,
    )


def _ensure_chrome_ready() -> None:
    _osascript('tell application "Google Chrome" to activate')


def _read_active_tab() -> dict[str, str]:
    script = r'''
tell application "Google Chrome"
  set theTitle to title of active tab of front window
  set theUrl to URL of active tab of front window
  set theBody to execute active tab of front window javascript "document.body ? document.body.innerText : ''"
end tell
return theTitle & "\n---XHS_URL---\n" & theUrl & "\n---XHS_BODY---\n" & theBody
'''
    raw = _osascript(script)
    if "Not authorised to send Apple events" in raw or "JavaScript" in raw and "not allowed" in raw:
        raise RuntimeError("Chrome 未允许 AppleScript 读取页面。请在 Chrome 菜单 View/显示 > Developer/开发者 中开启 Allow JavaScript from Apple Events。")
    parts = raw.split("\n---XHS_URL---\n", 1)
    title = parts[0].strip() if parts else ""
    rest = parts[1] if len(parts) > 1 else ""
    url_part, _, body = rest.partition("\n---XHS_BODY---\n")
    return {"title": title.strip(), "url": url_part.strip(), "body": body.strip()}


def _osascript(script: str) -> str:
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout.strip()


def _clean_title(title: str) -> str:
    title = re.sub(r"\s*-\s*小红书.*$", "", title).strip()
    return title[:120]


def _clean_body(body: str) -> str:
    lines = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        if line in {"首页", "发现", "消息", "我", "登录", "打开看看"}:
            continue
        lines.append(line)
    return "\n".join(lines)


def _title_from_body(body: str) -> str:
    for line in body.splitlines():
        line = line.strip()
        if 4 <= len(line) <= 80 and not re.search(r"^(赞|收藏|评论|分享|关注)$", line):
            return line
    return ""


def _looks_login_or_blocked(body: str) -> bool:
    if not body:
        return True
    signals = ("登录后查看更多", "扫码登录", "验证码登录", "请完成验证")
    return any(signal in body for signal in signals) and len(body) < 500


def _extract_metric(body: str, labels: tuple[str, ...]) -> int:
    for label in labels:
        patterns = [
            rf"{label}\s*([0-9]+(?:\.[0-9]+)?)\s*([万wWkK]?)",
            rf"([0-9]+(?:\.[0-9]+)?)\s*([万wWkK]?)\s*{label}",
        ]
        for pattern in patterns:
            match = re.search(pattern, body)
            if match:
                return _parse_number(match.group(1), match.group(2))
    return 0


def _parse_number(value: str, unit: str) -> int:
    number = float(value)
    if unit in {"万", "w", "W"}:
        number *= 10000
    elif unit in {"k", "K"}:
        number *= 1000
    return int(number)


def _extract_published_at(body: str) -> datetime | None:
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


def _published_datetime(year: int, month: int, day: int, hour: str | None, minute: str | None) -> datetime:
    return datetime(
        year,
        month,
        day,
        int(hour or 0),
        int(minute or 0),
        tzinfo=ZoneInfo("Asia/Shanghai"),
    )


def _note_id_from_url(url: str) -> str:
    match = re.search(r"/(?:explore|discovery/item)/([0-9a-fA-F]+)", url)
    if match:
        return match.group(1)
    import hashlib

    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
