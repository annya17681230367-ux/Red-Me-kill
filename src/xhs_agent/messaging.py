from __future__ import annotations

import mimetypes
from pathlib import Path

import httpx

from .config import Settings, WeChatOfficialAccountSettings, WeComSettings
from .reports import ReportResult


REPORT_NOTICE = "小红书【Red Me Kill】日报已生成，请注意查收～"


class WeComClient:
    def __init__(self, settings: WeComSettings):
        self.settings = settings

    def enabled(self) -> bool:
        return bool(self.settings.enabled and self.settings.webhook_url)

    def send_markdown(self, markdown_text: str) -> None:
        if not self.enabled():
            return
        if "qyapi.weixin.qq.com/cgi-bin/webhook/send" not in self.settings.webhook_url:
            raise RuntimeError("企业微信 webhook_url 不是发送 Webhook，请填写 qyapi.weixin.qq.com/cgi-bin/webhook/send?key=... 格式的地址。")
        response = httpx.post(
            self.settings.webhook_url,
            json={"msgtype": "markdown", "markdown": {"content": _limit_bytes(markdown_text, 3500)}},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errcode") != 0:
            raise RuntimeError(f"企业微信发送失败：{payload}")

    def send_report(self, result: ReportResult) -> None:
        if not self.enabled():
            return
        if result.pdf_path.exists():
            self.send_file(result.pdf_path)

    def send_file(self, file_path: Path) -> None:
        if not self.enabled():
            return
        upload_url = self.settings.webhook_url.replace("/send?", "/upload_media?") + "&type=file"
        mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        with file_path.open("rb") as f:
            response = httpx.post(
                upload_url,
                files={"media": (file_path.name, f, mime_type)},
                timeout=60,
            )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errcode") != 0:
            raise RuntimeError(f"企业微信文件上传失败：{payload}")
        media_id = payload.get("media_id")
        if not media_id:
            raise RuntimeError(f"企业微信文件上传未返回 media_id：{payload}")
        response = httpx.post(
            self.settings.webhook_url,
            json={"msgtype": "file", "file": {"media_id": media_id}},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errcode") != 0:
            raise RuntimeError(f"企业微信文件发送失败：{payload}")


class WeChatOfficialAccountClient:
    def __init__(self, settings: WeChatOfficialAccountSettings):
        self.settings = settings

    def enabled(self) -> bool:
        return bool(self.settings.enabled and self.settings.app_id and self.settings.app_secret and self.settings.openids)

    def access_token(self) -> str:
        response = httpx.get(
            "https://api.weixin.qq.com/cgi-bin/token",
            params={
                "grant_type": "client_credential",
                "appid": self.settings.app_id,
                "secret": self.settings.app_secret,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if "access_token" not in payload:
            raise RuntimeError(f"微信公众号授权失败：{payload}")
        return payload["access_token"]

    def send_text(self, text: str) -> None:
        if not self.enabled():
            return
        token = self.access_token()
        for openid in self.settings.openids:
            response = httpx.post(
                "https://api.weixin.qq.com/cgi-bin/message/custom/send",
                params={"access_token": token},
                json={"touser": openid, "msgtype": "text", "text": {"content": text[:1900]}},
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("errcode") != 0:
                raise RuntimeError(f"微信公众号发送失败：{payload}")


def deliver_report(settings: Settings, result: ReportResult, dry_run: bool = False) -> None:
    if dry_run:
        return
    text = _summary_text(result)
    errors: list[str] = []

    if settings.report.send_to_feishu:
        from .feishu import FeishuClient

        try:
            FeishuClient(settings.feishu).send_text(text)
        except Exception as exc:
            errors.append(f"飞书发送失败：{exc}")

    try:
        WeComClient(settings.wecom).send_report(result)
    except Exception as exc:
        errors.append(f"企业微信发送失败：{exc}")

    try:
        WeChatOfficialAccountClient(settings.wechat_official_account).send_text(text)
    except Exception as exc:
        errors.append(f"微信发送失败：{exc}")

    for error in errors:
        print(error)


def _summary_text(result: ReportResult) -> str:
    return f"{REPORT_NOTICE}\nMarkdown：{result.markdown_path.resolve()}\nHTML：{result.html_path.resolve()}\nPDF：{result.pdf_path.resolve()}"


def _document_links(result: ReportResult) -> str:
    return (
        f"> 文档链接：{result.html_path.resolve()}\n"
        f"> PDF报告：{result.pdf_path.resolve()}"
    )


def _limit_bytes(text: str, limit: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    return encoded[:limit].decode("utf-8", errors="ignore") + "\n\n> 内容过长，完整版本请查看 PDF 报告。"


def _wecom_markdown(result: ReportResult) -> str:
    title = result.feishu_summary.replace("：", "\n> ")
    return (
        f"**{title}**\n"
        f"> Markdown：{result.markdown_path.resolve()}\n"
        f"> HTML：{result.html_path.resolve()}\n"
        f"> 请打开报告查看账号表现、笔记诊断和优化动作。"
    )


def _split_markdown(text: str, limit: int) -> list[str]:
    lines = text.strip().splitlines()
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in lines:
        add_len = len(line) + 1
        if current and current_len + add_len > limit:
            chunks.append("\n".join(current).strip())
            current = []
            current_len = 0
        current.append(line)
        current_len += add_len
    if current:
        chunks.append("\n".join(current).strip())
    return chunks or [text[:limit]]


def _compact_report(markdown_text: str) -> str:
    lines = markdown_text.strip().splitlines()
    out: list[str] = []
    current_note_lines: list[str] = []
    note_count = 0
    in_note = False
    keep_table = False

    def flush_note() -> None:
        nonlocal current_note_lines, note_count
        if not current_note_lines or note_count >= 5:
            current_note_lines = []
            return
        out.extend(current_note_lines[:7])
        note_count += 1
        current_note_lines = []

    for line in lines:
        if line.startswith("# "):
            flush_note()
            out.append(line)
            continue
        if line.startswith("- 今日") or line.startswith("- 本周"):
            out.append(line)
            continue
        if line.startswith("## 今日爆贴数据") or line.startswith("## 本周爆贴数据"):
            flush_note()
            out.extend(["", line])
            keep_table = True
            continue
        if keep_table:
            if line.startswith("|") or "爆贴共性" in line or not line:
                out.append(line)
                continue
            keep_table = False
        if line.startswith("## 今日笔记诊断") or line.startswith("## 高优先级笔记"):
            flush_note()
            out.extend(["", line])
            continue
        if line.startswith("## 下周运营策略") or line.startswith("## 账号数据变化"):
            flush_note()
            out.extend(["", line])
            continue
        if line.startswith("### "):
            flush_note()
            in_note = True
            current_note_lines = ["", line]
            continue
        if in_note:
            if line.startswith("- 链接：") or line.startswith("- 数据：") or line.startswith("- 评分："):
                current_note_lines.append(line)
            elif line.startswith("- 模型总结："):
                summary = line.replace("Client error '402 Payment Required' for url 'https://api.deepseek.com/chat/completions'", "DeepSeek API 余额不足")
                current_note_lines.append(summary)
            elif line.startswith("- 主要问题："):
                current_note_lines.append(_shorten_semicolon_line(line, 2))
            elif line.startswith("- 执行动作："):
                current_note_lines.append(_shorten_semicolon_line(line, 3))
            elif line.startswith("- 下一步："):
                current_note_lines.append(line)
            continue
        if line.startswith("|") and "账号" in line:
            out.append(line)
        elif line.startswith("|---"):
            out.append(line)
        elif line.startswith("|") and len(out) < 120:
            out.append(line)
        elif line[:2] in {"1.", "2.", "3.", "4."}:
            out.append(line)

    flush_note()
    if not out:
        return markdown_text[:3600]
    return "\n".join(out).strip()


def _shorten_semicolon_line(line: str, limit: int) -> str:
    if "：" not in line:
        return line
    prefix, rest = line.split("：", 1)
    parts = [part.strip() for part in rest.split("；") if part.strip()]
    return f"{prefix}：" + "；".join(parts[:limit])
