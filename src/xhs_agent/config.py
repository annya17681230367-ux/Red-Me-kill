from __future__ import annotations

import csv
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

from .models import Account


class AgentSettings(BaseModel):
    timezone: str = "Asia/Shanghai"
    database_path: str = "data/xhs_agent.sqlite3"
    reports_dir: str = "data/reports"
    accounts_csv: str = "config/accounts.csv"
    manual_links_csv: str = "data/manual_links.csv"
    knowledge_file: str = "knowledge/xhs_strategy.md"


class WeChatInputSettings(BaseModel):
    enabled: bool = True
    transcript_path: str = "data/wechat_messages.txt"


class ScheduleSettings(BaseModel):
    daily_report_time: str = "13:00"
    weekly_report_day: str = "thu"
    weekly_report_time: str = "21:30"


class FeishuSettings(BaseModel):
    app_id: str = ""
    app_secret: str = ""
    chat_name: str = "学管部小红书发帖群"
    chat_id: str = ""
    message_lookback_hours: int = 30


class WeComSettings(BaseModel):
    webhook_url: str = ""
    bot_profile_url: str = ""
    enabled: bool = False


class WeChatOfficialAccountSettings(BaseModel):
    app_id: str = ""
    app_secret: str = ""
    openids: list[str] = Field(default_factory=list)
    enabled: bool = False


class LlmSettings(BaseModel):
    enabled: bool = False
    provider: str = "deepseek"
    base_url: str = "https://api.deepseek.com"
    ollama_base_url: str = "http://localhost:11434"
    anthropic_base_url: str = "https://api.anthropic.com"
    api_key: str = ""
    model: str = "deepseek-v4-flash"
    timeout_seconds: int = 45
    max_tokens: int = 1600
    temperature: float = 0.3
    input_token_usd_per_million: float = 0.14
    output_token_usd_per_million: float = 0.28


class ImageGenerationSettings(BaseModel):
    enabled: bool = False
    provider: str = "openai_compatible"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    output_dir: str = "data/generated_images"
    timeout_seconds: int = 90


class XhsApiSettings(BaseModel):
    base_url: str = ""
    api_key: str = ""
    app_id: str = ""
    version: str = "v3"
    note_method: str = ""
    account_method: str = ""
    auth_mode: str = "ark_common_controller"
    timeout_seconds: int = 30


class ReportSettings(BaseModel):
    primary_goals: list[str] = Field(default_factory=lambda: ["私信", "互动", "涨粉"])
    send_to_feishu: bool = True
    include_html: bool = True


class Settings(BaseModel):
    agent: AgentSettings = Field(default_factory=AgentSettings)
    schedule: ScheduleSettings = Field(default_factory=ScheduleSettings)
    feishu: FeishuSettings = Field(default_factory=FeishuSettings)
    wechat_input: WeChatInputSettings = Field(default_factory=WeChatInputSettings)
    wecom: WeComSettings = Field(default_factory=WeComSettings)
    wechat_official_account: WeChatOfficialAccountSettings = Field(default_factory=WeChatOfficialAccountSettings)
    llm: LlmSettings = Field(default_factory=LlmSettings)
    image_generation: ImageGenerationSettings = Field(default_factory=ImageGenerationSettings)
    xhs_api: XhsApiSettings = Field(default_factory=XhsApiSettings)
    report: ReportSettings = Field(default_factory=ReportSettings)


def load_settings(path: str | Path = "config/settings.toml") -> Settings:
    config_path = Path(path)
    if not config_path.exists():
        example = Path("config/settings.example.toml")
        raise FileNotFoundError(f"缺少配置文件：{config_path}。请复制 {example} 后填写。")
    with config_path.open("rb") as f:
        data: dict[str, Any] = tomllib.load(f)
    settings = Settings.model_validate(data)
    return _apply_env_overrides(settings)


def _apply_env_overrides(settings: Settings) -> Settings:
    updates = {}
    if os.getenv("XHS_LLM_ENABLED"):
        updates["enabled"] = os.getenv("XHS_LLM_ENABLED", "").lower() in {"1", "true", "yes", "on"}
    if os.getenv("XHS_LLM_PROVIDER"):
        updates["provider"] = os.environ["XHS_LLM_PROVIDER"]
    if os.getenv("XHS_LLM_BASE_URL"):
        updates["base_url"] = os.environ["XHS_LLM_BASE_URL"]
    if os.getenv("XHS_LLM_ANTHROPIC_BASE_URL"):
        updates["anthropic_base_url"] = os.environ["XHS_LLM_ANTHROPIC_BASE_URL"]
    if os.getenv("XHS_LLM_API_KEY"):
        updates["api_key"] = os.environ["XHS_LLM_API_KEY"]
    if os.getenv("XHS_LLM_MODEL"):
        updates["model"] = os.environ["XHS_LLM_MODEL"]
    if os.getenv("XHS_LLM_INPUT_TOKEN_USD_PER_MILLION"):
        updates["input_token_usd_per_million"] = float(os.environ["XHS_LLM_INPUT_TOKEN_USD_PER_MILLION"])
    if os.getenv("XHS_LLM_OUTPUT_TOKEN_USD_PER_MILLION"):
        updates["output_token_usd_per_million"] = float(os.environ["XHS_LLM_OUTPUT_TOKEN_USD_PER_MILLION"])
    if updates:
        settings.llm = settings.llm.model_copy(update=updates)
    return settings


def load_accounts(path: str | Path) -> list[Account]:
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"缺少账号表：{csv_path}")
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        return [Account(**row) for row in csv.DictReader(f) if row.get("account_id")]


def load_manual_links(path: str | Path):
    from .models import FeishuLink

    csv_path = Path(path)
    if not csv_path.exists():
        return []
    links = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            url = (row.get("url") or "").strip()
            note_id = (row.get("note_id") or "").strip()
            if not url and note_id:
                url = f"xhs-note-id://{note_id}"
            if not url:
                continue
            submitted_at = _parse_datetime(row.get("submitted_at") or "")
            submission_id = row.get("submission_id") or f"manual-{url}"
            sender_name = row.get("sender_name") or "manual"
            links.append(FeishuLink(submission_id, sender_name, submitted_at, url))
    return links


XHS_LINK_RE = re.compile(r"https?://(?:www\.)?(?:xiaohongshu\.com|xhslink\.com|t\.cn)/[^\s\"'<>，。]+")


def load_wechat_transcript_links(path: str | Path):
    from datetime import datetime

    from .models import FeishuLink

    transcript_path = Path(path)
    if not transcript_path.exists():
        return []
    text = transcript_path.read_text(encoding="utf-8", errors="ignore")
    links = []
    for idx, url in enumerate(dict.fromkeys(XHS_LINK_RE.findall(text))):
        links.append(
            FeishuLink(
                message_id=f"wechat-transcript-{idx}-{url}",
                sender_name="wechat",
                sent_at=datetime.now(),
                url=url,
            )
        )
    return links


def _parse_datetime(value: str) -> datetime:
    if not value:
        return datetime.now()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return datetime.fromisoformat(value)
