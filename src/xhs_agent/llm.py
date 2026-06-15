from __future__ import annotations

import json
from dataclasses import replace

import httpx

from .config import LlmSettings
from .models import NoteAnalysis, NoteMetrics


class DeepSeekClient:
    def __init__(self, settings: LlmSettings, knowledge: str = ""):
        self.settings = settings
        self.knowledge = knowledge

    def enabled(self) -> bool:
        if not self.settings.enabled:
            return False
        if self.settings.provider == "deepseek":
            return bool(self.settings.api_key)
        if self.settings.provider == "ollama":
            return bool(self.settings.model)
        return False

    def enrich_note_analysis(self, note: NoteMetrics, base: NoteAnalysis) -> NoteAnalysis:
        if not self.enabled():
            return base
        try:
            payload = self._call(note, base)
            return self._merge(base, payload)
        except Exception as exc:
            return replace(base, llm_provider="rules", llm_summary=f"DeepSeek 调用失败，已使用规则分析：{exc}")

    def _call(self, note: NoteMetrics, base: NoteAnalysis) -> dict:
        if self.settings.provider == "ollama":
            return self._call_ollama(note, base)
        response = httpx.post(
            f"{self.settings.base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.model,
                "temperature": self.settings.temperature,
                "max_tokens": self.settings.max_tokens,
                "messages": [
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": self._user_prompt(note, base)},
                ],
            },
            timeout=self.settings.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return _parse_json(content)

    def _call_ollama(self, note: NoteMetrics, base: NoteAnalysis) -> dict:
        response = httpx.post(
            f"{self.settings.ollama_base_url.rstrip('/')}/api/chat",
            json={
                "model": self.settings.model,
                "stream": False,
                "options": {
                    "temperature": self.settings.temperature,
                    "num_predict": self.settings.max_tokens,
                },
                "messages": [
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": self._user_prompt(note, base)},
                ],
            },
            timeout=self.settings.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "")
        return _parse_json(content)

    def _system_prompt(self) -> str:
        return (
            "你是小红书运营分析 Agent，目标是帮助教育/升学类账号提升私信、互动和涨粉。"
            "输出必须具体、可执行，避免空泛建议。只返回 JSON，不要 Markdown。"
        )

    def _user_prompt(self, note: NoteMetrics, base: NoteAnalysis) -> str:
        body = (note.body or "")[:1800]
        knowledge = self.knowledge[:2200]
        return json.dumps(
            {
                "knowledge": knowledge,
                "note": {
                    "url": note.url,
                    "title": note.title,
                    "body": body,
                    "likes": note.likes,
                    "collects": note.collects,
                    "comments": note.comments,
                    "shares": note.shares,
                    "views": note.views,
                    "leads": note.leads,
                },
                "base_analysis": {
                    "scores": {
                        "topic": base.topic_score,
                        "title": base.title_score,
                        "cover": base.cover_score,
                        "body": base.body_score,
                        "conversion": base.conversion_score,
                    },
                    "issues": base.issues,
                    "actions": base.actions,
                    "content_type": base.content_type,
                },
                "required_json_schema": {
                    "llm_summary": "一句话总结这条笔记最大机会和最大问题",
                    "strengths": ["最多3条亮点"],
                    "issues": ["最多3条问题"],
                    "actions": ["最多5条可执行动作，含标题/封面/正文/评论/私信"],
                    "next_step": "继续放大/轻微优化/复盘重写之一，并说明原因",
                    "funnel_diagnosis": ["最多3条漏斗诊断"],
                    "nine_dimension_review": ["选题/标题/封面/结构/复用等九维要点，最多6条"],
                },
            },
            ensure_ascii=False,
        )

    def _merge(self, base: NoteAnalysis, payload: dict) -> NoteAnalysis:
        return replace(
            base,
            strengths=_list_or_base(payload.get("strengths"), base.strengths),
            issues=_list_or_base(payload.get("issues"), base.issues),
            actions=_list_or_base(payload.get("actions"), base.actions),
            next_step=str(payload.get("next_step") or base.next_step),
            funnel_diagnosis=_list_or_base(payload.get("funnel_diagnosis"), base.funnel_diagnosis),
            nine_dimension_review=_list_or_base(payload.get("nine_dimension_review"), base.nine_dimension_review),
            llm_provider=f"{self.settings.provider}:{self.settings.model}",
            llm_summary=str(payload.get("llm_summary") or ""),
        )


def _parse_json(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end >= start:
        text = text[start : end + 1]
    return json.loads(text)


def _list_or_base(value, base: list[str]) -> list[str]:
    if isinstance(value, list):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return cleaned or base
    return base
