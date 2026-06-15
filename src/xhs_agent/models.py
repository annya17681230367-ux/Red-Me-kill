from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Account:
    account_id: str
    account_name: str
    operator: str
    profile_url: str
    niche: str = ""
    stage: str = ""
    notes: str = ""


@dataclass(frozen=True)
class FeishuLink:
    message_id: str
    sender_name: str
    sent_at: datetime
    url: str


@dataclass(frozen=True)
class ManualSubmission:
    submission_id: str
    sender_name: str
    submitted_at: datetime
    url: str
    account_id: str | None = None
    note_id: str | None = None


@dataclass(frozen=True)
class NoteMetrics:
    note_id: str
    url: str
    account_id: str | None
    title: str
    body: str
    published_at: datetime | None
    likes: int = 0
    collects: int = 0
    comments: int = 0
    shares: int = 0
    views: int = 0
    leads: int = 0

    @property
    def engagement(self) -> int:
        return self.likes + self.collects + self.comments + self.shares


@dataclass(frozen=True)
class AccountSnapshot:
    account_id: str
    captured_at: datetime
    followers: int = 0
    following: int = 0
    liked_and_collected: int = 0
    notes_count: int = 0
    leads: int = 0


@dataclass(frozen=True)
class NoteAnalysis:
    note_id: str
    topic_score: int
    title_score: int
    cover_score: int
    body_score: int
    conversion_score: int
    strengths: list[str]
    issues: list[str]
    actions: list[str]
    next_step: str
    funnel_diagnosis: list[str]
    nine_dimension_review: list[str]
    content_type: str
    topic_matrix_score: int
    llm_provider: str = "rules"
    llm_summary: str = ""

    @property
    def total_score(self) -> float:
        return round(
            (
                self.topic_score
                + self.title_score
                + self.cover_score
                + self.body_score
                + self.conversion_score
            )
            / 5,
            1,
        )
