from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from .config import XhsApiSettings
from .models import Account, AccountSnapshot, NoteMetrics


class XhsApiClient:
    def __init__(self, settings: XhsApiSettings):
        self.settings = settings

    def enabled(self) -> bool:
        return bool(self.settings.base_url and self.settings.api_key and self.settings.app_id)

    def fetch_note(self, url: str) -> NoteMetrics:
        if not self.enabled() or not self.settings.note_method:
            return self._placeholder_note(url)
        data = self._call_common_controller(
            self.settings.note_method,
            {"url": url},
        )
        return self._parse_note(url, data)

    def fetch_account_snapshot(self, account: Account) -> AccountSnapshot:
        if not self.enabled() or not self.settings.account_method:
            return AccountSnapshot(account_id=account.account_id, captured_at=datetime.now(timezone.utc))
        data = self._call_common_controller(
            self.settings.account_method,
            {"profile_url": account.profile_url, "account_id": account.account_id},
        )
        return AccountSnapshot(
            account_id=account.account_id,
            captured_at=datetime.now(timezone.utc),
            followers=int(data.get("followers", 0) or 0),
            following=int(data.get("following", 0) or 0),
            liked_and_collected=int(data.get("liked_and_collected", data.get("likes_collects", 0)) or 0),
            notes_count=int(data.get("notes_count", 0) or 0),
            leads=int(data.get("leads", data.get("private_messages", 0)) or 0),
        )

    def _call_common_controller(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        request_payload = {
            "appId": self.settings.app_id,
            "timestamp": int(time.time() * 1000),
            "version": self.settings.version,
            "method": method,
            "data": payload,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }
        response = httpx.post(
            self.settings.base_url,
            json=request_payload,
            headers=headers,
            timeout=self.settings.timeout_seconds,
        )
        response.raise_for_status()
        raw = response.json()
        if isinstance(raw, dict) and raw.get("code") not in (None, 0, "0", 200, "200"):
            raise RuntimeError(f"小红书 API 返回错误：{raw}")
        return self._unwrap_data(raw)

    def _unwrap_data(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            return {}
        data = raw.get("data", raw)
        if isinstance(data, dict) and "result" in data:
            data = data["result"]
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        return data if isinstance(data, dict) else {}

    def _parse_note(self, url: str, data: dict[str, Any]) -> NoteMetrics:
        published_at = None
        if data.get("published_at"):
            published_at = datetime.fromisoformat(str(data["published_at"]).replace("Z", "+00:00"))
        return NoteMetrics(
            note_id=str(data.get("note_id") or self._stable_id(url)),
            url=url,
            account_id=data.get("account_id"),
            title=str(data.get("title") or ""),
            body=str(data.get("body") or data.get("content") or ""),
            published_at=published_at,
            likes=int(data.get("likes", 0) or 0),
            collects=int(data.get("collects", data.get("favorites", 0)) or 0),
            comments=int(data.get("comments", 0) or 0),
            shares=int(data.get("shares", 0) or 0),
            views=int(data.get("views", 0) or 0),
            leads=int(data.get("leads", data.get("private_messages", 0)) or 0),
        )

    def _placeholder_note(self, url: str) -> NoteMetrics:
        reason = "未配置小红书数据 API，当前为占位数据。"
        if self.enabled() and not self.settings.note_method:
            reason = "小红书 Ark API 已配置，但缺少查询笔记数据的 note_method，当前为占位数据。"
        return NoteMetrics(
            note_id=self._stable_id(url),
            url=url,
            account_id=None,
            title="待抓取标题",
            body=reason,
            published_at=None,
        )

    @staticmethod
    def _stable_id(url: str) -> str:
        return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
