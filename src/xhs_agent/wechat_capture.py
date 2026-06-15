from __future__ import annotations

import csv
import hashlib
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import XHS_LINK_RE


@dataclass(frozen=True)
class CapturedLink:
    submission_id: str
    sender_name: str
    submitted_at: str
    url: str
    account_id: str = ""
    note_id: str = ""


def import_clipboard_to_manual_links(manual_links_csv: str, sender_name: str = "wechat") -> int:
    text = read_macos_clipboard()
    return append_links_from_text(manual_links_csv, text, sender_name)


def watch_clipboard(manual_links_csv: str, sender_name: str = "wechat", interval_seconds: float = 2.0) -> None:
    print("开始监听剪贴板。请在微信里复制包含小红书链接的群消息；按 Ctrl+C 停止。")
    last_digest = ""
    while True:
        text = read_macos_clipboard()
        digest = hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()
        if text and digest != last_digest:
            added = append_links_from_text(manual_links_csv, text, sender_name)
            if added:
                print(f"已捕获 {added} 条小红书链接。")
            last_digest = digest
        time.sleep(interval_seconds)


def append_links_from_text(manual_links_csv: str, text: str, sender_name: str = "wechat") -> int:
    links = list(dict.fromkeys(XHS_LINK_RE.findall(text or "")))
    if not links:
        return 0

    path = Path(manual_links_csv)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _existing_urls(path)
    rows = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for url in links:
        if url in existing:
            continue
        rows.append(
            CapturedLink(
                submission_id=f"wechat-{hashlib.sha1(url.encode('utf-8')).hexdigest()[:12]}",
                sender_name=sender_name,
                submitted_at=now,
                url=url,
            )
        )
    if not rows:
        return 0

    file_exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["submission_id", "sender_name", "submitted_at", "url", "account_id", "note_id"],
        )
        if not file_exists or path.stat().st_size == 0:
            writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)
    return len(rows)


def read_macos_clipboard() -> str:
    result = subprocess.run(["pbpaste"], capture_output=True, check=False)
    raw = result.stdout or b""
    for encoding in ("utf-8", "gb18030", "utf-16"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="ignore")


def _existing_urls(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return {row.get("url", "") for row in csv.DictReader(f) if row.get("url")}
