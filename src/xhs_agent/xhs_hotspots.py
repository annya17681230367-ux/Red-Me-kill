from __future__ import annotations

import csv
import json
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from urllib.parse import quote


@dataclass(frozen=True)
class HotspotNote:
    keyword: str
    title: str
    author: str
    likes: int
    url: str
    reason: str


MONTH_KEYWORDS = {
    6: [
        "英国留学生 dissertation proposal",
        "英国留学生 毕业论文 导师",
        "澳洲留学生 S1 出分 挂科",
        "澳洲留学生 appeal 申诉",
        "美国留学生 summer school",
    ],
}


def collect_daily_hotspots(report_date: date, output_dir: str = "data/hotspots", limit: int = 5) -> Path:
    keywords = MONTH_KEYWORDS.get(report_date.month, _default_keywords(report_date.month))
    results: list[HotspotNote] = []
    for keyword in keywords:
        try:
            results.extend(_search_keyword(keyword))
        except Exception:
            continue
    selected = _select_hotspots(results, limit)
    output_path = Path(output_dir) / f"daily-{report_date.isoformat()}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([asdict(item) for item in selected], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_csv(output_path.with_suffix(".csv"), selected)
    return output_path


def load_daily_hotspots(report_date: date, output_dir: str = "data/hotspots") -> list[dict]:
    path = Path(output_dir) / f"daily-{report_date.isoformat()}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _search_keyword(keyword: str) -> list[HotspotNote]:
    url = f"https://www.xiaohongshu.com/search_result?keyword={quote(keyword)}&source=web_search_result_notes"
    _osascript(f'tell application "Google Chrome" to open location "{url}"')
    time.sleep(7)
    body = _read_body()
    links = _read_result_links()
    return _parse_search_body(keyword, body, links)


def _parse_search_body(keyword: str, body: str, links: dict[str, str]) -> list[HotspotNote]:
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    items: list[HotspotNote] = []
    for idx, line in enumerate(lines):
        if line not in links or _skip_line(line) or not _looks_like_title(line):
            continue
        author = ""
        likes = None
        nearby = lines[idx + 1 : idx + 5]
        if not any(_looks_like_date(line) for line in nearby):
            continue
        for next_line in nearby:
            parsed_like = _parse_like(next_line)
            if likes is None and parsed_like is not None:
                likes = parsed_like
            if not author and not next_line.isdigit() and not _looks_like_title(next_line):
                author = re.split(r"\s+\|?\s*(?:\d{4}-\d{2}-\d{2}|\d{2}-\d{2}|\d+分钟前|\d+小时前|\d+天前)", next_line)[0].strip()
        if likes is None:
            continue
        items.append(
            HotspotNote(
                keyword=keyword,
                title=line[:80],
                author=author[:30] or "-",
                likes=likes,
                url=links.get(line, ""),
                reason=_reason_for_keyword(keyword),
            )
        )
    return items


def _read_body() -> str:
    script = r'''
tell application "Google Chrome"
  set theBody to execute active tab of front window javascript "document.body ? document.body.innerText : ''"
end tell
return theBody
'''
    return _osascript(script)


def _read_result_links() -> dict[str, str]:
    script = (
        'tell application "Google Chrome" to tell active tab of front window to execute javascript '
        '"Array.from(document.querySelectorAll(\'a\')).filter(a => a.innerText.trim().length > 0 && a.href.includes(\'/search_result/\')).map(a => a.innerText.trim() + \'=>\' + a.href).join(\'\\\\n\')"'
    )
    raw = _osascript(script)
    links = {}
    for line in raw.splitlines():
        title, _, url = line.partition("=>")
        title = title.strip()
        if title and url:
            links[title] = url.strip()
    return links


def _select_hotspots(items: list[HotspotNote], limit: int) -> list[HotspotNote]:
    deduped = {}
    for item in items:
        if item.likes < 200:
            continue
        key = item.title
        current = deduped.get(key)
        if current is None or item.likes > current.likes:
            deduped[key] = item
    return sorted(deduped.values(), key=lambda item: item.likes, reverse=True)[:limit]


def _parse_like(line: str) -> int | None:
    if not re.fullmatch(r"\d+(?:\.\d+)?[万wWkK]?", line):
        return None
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([万wWkK]?)", line)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2)
    if unit in {"万", "w", "W"}:
        number *= 10000
    elif unit in {"k", "K"}:
        number *= 1000
    return int(number)


def _looks_like_date(line: str) -> bool:
    return bool(
        re.fullmatch(r"\d{4}-\d{2}-\d{2}", line)
        or re.fullmatch(r"\d{2}-\d{2}", line)
        or re.fullmatch(r"\d+分钟前", line)
        or re.fullmatch(r"\d+小时前", line)
        or re.fullmatch(r"\d+天前", line)
    )


def _looks_like_title(line: str) -> bool:
    if len(line) < 8 or len(line) > 90:
        return False
    if any(word in line.lower() for word in ("intern", "实习", "ootd", "vlog", "租房", "旅游")):
        return False
    if re.fullmatch(r"[\d.万wWkK]+", line):
        return False
    return any(token in line.lower() for token in ("留学", "dissertation", "proposal", "summer school", "挂科", "申诉", "appeal", "论文", "导师", "暑课", "作业", "essay", "quiz", "exam"))


def _skip_line(line: str) -> bool:
    skip = {"全部", "图文", "视频", "用户", "筛选", "综合", "相关搜索", "活动", "发现", "发布", "通知", "我"}
    return line in skip or line.startswith("沪ICP备") or line.startswith("© ")


def _reason_for_keyword(keyword: str) -> str:
    if "英国" in keyword:
        return "贴合6月英国毕业论文/Proposal启动期，可拆成时间线、导师沟通、开题避坑。"
    if "澳洲" in keyword:
        return "贴合6月澳洲S1出分和挂科申诉焦虑，可做流程型与补救型内容。"
    if "美国" in keyword:
        return "贴合美国暑课补学分场景，可做节奏管理和作业密集期内容。"
    return "贴合当月留学生课业痛点，适合作为选题参考。"


def _default_keywords(month: int) -> list[str]:
    return [
        "英国留学生 热点 论文",
        "澳洲留学生 热点 作业",
        "美国留学生 热点 课程",
        f"{month}月 留学生 论文",
        f"{month}月 留学生 挂科",
    ]


def _write_csv(path: Path, items: list[HotspotNote]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["keyword", "title", "author", "likes", "url", "reason"])
        writer.writeheader()
        for item in items:
            writer.writerow(asdict(item))


def _osascript(script: str) -> str:
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout.strip()
