from __future__ import annotations

import re

from .models import NoteAnalysis, NoteMetrics
from .llm import DeepSeekClient


PAIN_WORDS = ("避坑", "后悔", "不要", "必看", "方法", "清单", "步骤", "对比", "真实", "案例", "私信", "咨询")


class XhsAnalyzer:
    def __init__(self, knowledge: str = "", llm_client: DeepSeekClient | None = None):
        self.knowledge = knowledge
        self.llm_client = llm_client

    def analyze_note(self, note: NoteMetrics) -> NoteAnalysis:
        title = note.title or ""
        body = note.body or ""
        topic_score = self._score_topic(title, body)
        title_score = self._score_title(title)
        cover_score = 6 if title else 4
        body_score = self._score_body(body)
        conversion_score = self._score_conversion(note, body)

        strengths = self._strengths(note, title, body)
        issues = self._issues(title, body, note)
        actions = self._actions(title, body, note)
        next_step = self._next_step(note, (topic_score + title_score + body_score + conversion_score) / 4)
        funnel_diagnosis = self._funnel_diagnosis(note, title, body)
        nine_dimension_review = self._nine_dimension_review(note, title, body)
        content_type = self._content_type(title, body)
        topic_matrix_score = self._topic_matrix_score(note, title, body)

        base_analysis = NoteAnalysis(
            note_id=note.note_id,
            topic_score=topic_score,
            title_score=title_score,
            cover_score=cover_score,
            body_score=body_score,
            conversion_score=conversion_score,
            strengths=strengths,
            issues=issues,
            actions=actions,
            next_step=next_step,
            funnel_diagnosis=funnel_diagnosis,
            nine_dimension_review=nine_dimension_review,
            content_type=content_type,
            topic_matrix_score=topic_matrix_score,
        )
        if self.llm_client:
            return self.llm_client.enrich_note_analysis(note, base_analysis)
        return base_analysis

    def _score_topic(self, title: str, body: str) -> int:
        text = title + body
        score = 5
        if any(w in text for w in PAIN_WORDS):
            score += 2
        if re.search(r"\d", text):
            score += 1
        if any(w in text for w in ("家长", "学生", "新生", "考研", "升学", "留学", "择校")):
            score += 1
        return min(score, 10)

    def _score_title(self, title: str) -> int:
        if not title or title == "待抓取标题":
            return 4
        score = 5
        if 12 <= len(title) <= 28:
            score += 1
        if any(w in title for w in PAIN_WORDS):
            score += 2
        if re.search(r"\d", title):
            score += 1
        if "？" in title or "?" in title:
            score += 1
        return min(score, 10)

    def _score_body(self, body: str) -> int:
        if not body or "占位数据" in body:
            return 4
        score = 5
        if len(body) >= 180:
            score += 1
        if any(marker in body for marker in ("1.", "1、", "第一", "步骤", "总结")):
            score += 2
        if any(w in body for w in ("案例", "经验", "建议", "避坑")):
            score += 1
        return min(score, 10)

    def _score_conversion(self, note: NoteMetrics, body: str) -> int:
        score = 5
        if note.leads > 0:
            score += 3
        if note.comments >= 5:
            score += 1
        if any(w in body for w in ("评论", "想要", "资料", "咨询", "私信")):
            score += 1
        return min(score, 10)

    def _strengths(self, note: NoteMetrics, title: str, body: str) -> list[str]:
        strengths = []
        if note.engagement > 0:
            strengths.append(f"已有 {note.engagement} 次互动，可进入评论区做二次承接。")
        if any(w in title for w in PAIN_WORDS):
            strengths.append("标题包含痛点或利益点，具备点击基础。")
        if len(body) >= 180:
            strengths.append("正文信息量较完整，适合沉淀收藏。")
        return strengths or ["当前数据不足，先补齐标题、正文、封面和互动数据。"]

    def _issues(self, title: str, body: str, note: NoteMetrics) -> list[str]:
        issues = []
        if not title or title == "待抓取标题":
            issues.append("标题数据缺失，无法判断点击钩子。")
        elif len(title) < 10:
            issues.append("标题偏短，缺少人群、场景或结果。")
        if not body or "占位数据" in body:
            issues.append("正文数据缺失，无法判断结构和转化承接。")
        elif not any(marker in body for marker in ("1.", "1、", "第一", "步骤", "总结")):
            issues.append("正文结构不够清晰，建议拆成步骤、清单或案例复盘。")
        if note.leads == 0 and note.comments == 0:
            issues.append("暂未看到私信或评论信号，需要增强互动引导。")
        return issues[:3]

    def _actions(self, title: str, body: str, note: NoteMetrics) -> list[str]:
        topic = self._topic_hint(title, body)
        return [
            f"标题改写方向：{topic}避坑清单：这 3 个问题最容易影响咨询转化",
            f"封面建议：突出目标人群 + 结果，例如“{topic}家长必看 / 少走弯路”。",
            "评论区动作：置顶一个开放问题，收集需求后再私信承接，不做生硬引流。",
        ]

    def _funnel_diagnosis(self, note: NoteMetrics, title: str, body: str) -> list[str]:
        diagnosis = []
        if note.views and note.engagement:
            engagement_rate = note.engagement / note.views
            if engagement_rate < 0.03:
                diagnosis.append("互动率偏低：内容看完后缺少评论/收藏触发点，优先补充清单、对比或评论问题。")
            else:
                diagnosis.append(f"互动率约 {engagement_rate:.1%}：可继续观察评论需求并做私信承接。")
        elif not note.views:
            diagnosis.append("展现/阅读数据缺失：暂时无法判断流量漏斗断点。")
        if title == "待抓取标题" or not title:
            diagnosis.append("点击层缺失：需要补齐标题和封面数据，才能判断点击率问题。")
        elif self._score_title(title) < 7:
            diagnosis.append("点击层风险：标题钩子不够强，可能影响封面/标题点击率。")
        if note.leads == 0:
            diagnosis.append("转化层偏弱：暂未看到私信/线索，需要增强评论区引导和资料承接。")
        return diagnosis[:3]

    def _nine_dimension_review(self, note: NoteMetrics, title: str, body: str) -> list[str]:
        return [
            f"选题：{self._topic_hint(title, body)}方向，需确认目标人群是否足够具体。",
            f"标题：{self._title_formula(title)}",
            "封面：建议控制大字信息量，突出人群、痛点和结果。",
            "结构：开头先给结论，中段用步骤/案例/避坑，结尾设计评论问题。",
            "复用：保留表现好的痛点词、标题公式和评论问题，沉淀为系列模板。",
        ]

    def _content_type(self, title: str, body: str) -> str:
        text = title + body
        if any(w in text for w in ("教程", "步骤", "方法", "清单", "避坑", "攻略")):
            return "干货/教程类"
        if any(w in text for w in ("故事", "经历", "真实", "后悔", "我")):
            return "故事/共鸣类"
        if any(w in text for w in ("推荐", "测评", "种草", "产品", "工具")):
            return "产品/种草类"
        return "互动/话题类"

    def _topic_matrix_score(self, note: NoteMetrics, title: str, body: str) -> int:
        search_demand = 76 if any(w in title + body for w in ("攻略", "方法", "避坑", "清单")) else 55
        competition = 55
        account_fit = 88 if any(w in title + body for w in ("升学", "留学", "考研", "择校", "家长")) else 65
        timeliness = 70 if any(w in title + body for w in ("2026", "今年", "现在", "最新")) else 60
        differentiation = 72 if any(w in title + body for w in ("真实", "案例", "亲测", "复盘")) else 58
        score = (
            search_demand * 0.25
            + competition * 0.20
            + account_fit * 0.25
            + timeliness * 0.15
            + differentiation * 0.15
        )
        if note.leads > 0:
            score += 5
        return min(round(score), 100)

    def _next_step(self, note: NoteMetrics, avg_score: float) -> str:
        if note.leads > 0 or avg_score >= 8:
            return "继续放大：复刻选题结构，做同系列 2-3 篇。"
        if avg_score >= 6:
            return "轻微优化：优先改标题和封面，再观察 24 小时互动。"
        return "复盘重写：重新聚焦目标人群、痛点和评论承接。"

    def _topic_hint(self, title: str, body: str) -> str:
        text = title + body
        for word in ("升学", "留学", "考研", "择校", "新生", "家长", "私域"):
            if word in text:
                return word
        return "目标用户"

    def _title_formula(self, title: str) -> str:
        if not title or title == "待抓取标题":
            return "缺少标题，建议使用“人群 + 痛点 + 结果/清单”公式。"
        if re.search(r"\d", title) and any(w in title for w in PAIN_WORDS):
            return "包含数字和痛点词，可作为可复用标题公式。"
        return "建议补充数字、强场景或结果承诺，提高点击钩子。"
