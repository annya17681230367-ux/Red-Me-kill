from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .config import FeishuSettings
from .models import FeishuLink

XHS_LINK_RE = re.compile(r"https?://(?:www\.)?(?:xiaohongshu\.com|xhslink\.com)/[^\s\"'<>，。]+")


class FeishuClient:
    def __init__(self, settings: FeishuSettings):
        self.settings = settings
        self.base_url = "https://open.feishu.cn/open-apis"

    def enabled(self) -> bool:
        return bool(self.settings.app_id and self.settings.app_secret)

    def tenant_access_token(self) -> str:
        response = httpx.post(
            f"{self.base_url}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.settings.app_id, "app_secret": self.settings.app_secret},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 0:
            raise RuntimeError(f"飞书授权失败：{data}")
        return data["tenant_access_token"]

    def fetch_recent_xhs_links(self) -> list[FeishuLink]:
        if not self.enabled():
            return []

        token = self.tenant_access_token()
        chat_id = self.settings.chat_id or self.find_chat_id(token)
        if not chat_id:
            raise RuntimeError(f"未找到飞书群：{self.settings.chat_name}。请确认机器人已加入群聊，或手动填写 chat_id。")
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=self.settings.message_lookback_hours)
        params = {
            "container_id_type": "chat",
            "container_id": chat_id,
            "start_time": int(start.timestamp()),
            "end_time": int(end.timestamp()),
            "page_size": 50,
        }
        headers = {"Authorization": f"Bearer {token}"}
        links: list[FeishuLink] = []

        while True:
            response = httpx.get(
                f"{self.base_url}/im/v1/messages",
                params=params,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != 0:
                raise RuntimeError(f"读取飞书消息失败：{payload}")
            data = payload.get("data", {})
            for item in data.get("items", []):
                links.extend(self._extract_links(item))
            if not data.get("has_more"):
                break
            params["page_token"] = data.get("page_token")

        return links

    def send_text(self, text: str) -> None:
        if not self.enabled():
            return
        token = self.tenant_access_token()
        chat_id = self.settings.chat_id or self.find_chat_id(token)
        if not chat_id:
            raise RuntimeError(f"未找到飞书群：{self.settings.chat_name}。请确认机器人已加入群聊，或手动填写 chat_id。")
        response = httpx.post(
            f"{self.base_url}/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            headers={"Authorization": f"Bearer {token}"},
            json={
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"发送飞书消息失败：{payload}")

    def find_chat_id(self, token: str | None = None) -> str:
        token = token or self.tenant_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        params: dict[str, Any] = {"page_size": 100}
        while True:
            response = httpx.get(
                f"{self.base_url}/im/v1/chats",
                params=params,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != 0:
                raise RuntimeError(f"读取飞书群列表失败：{payload}")
            data = payload.get("data", {})
            for item in data.get("items", []):
                if item.get("name") == self.settings.chat_name:
                    return item.get("chat_id", "")
            if not data.get("has_more"):
                return ""
            params["page_token"] = data.get("page_token")

    def _extract_links(self, item: dict[str, Any]) -> list[FeishuLink]:
        raw_content = item.get("body", {}).get("content") or ""
        sender = item.get("sender", {}).get("sender_id", {}).get("user_id") or "unknown"
        try:
            decoded = json.loads(raw_content)
            text = json.dumps(decoded, ensure_ascii=False)
        except json.JSONDecodeError:
            text = raw_content
        sent_at = datetime.fromtimestamp(int(item.get("create_time", "0")) / 1000, timezone.utc)
        results = []
        for idx, url in enumerate(dict.fromkeys(XHS_LINK_RE.findall(text))):
            message_id = item.get("message_id", f"{sender}-{int(time.time())}-{idx}")
            results.append(FeishuLink(message_id=f"{message_id}-{idx}", sender_name=sender, sent_at=sent_at, url=url))
        return results
