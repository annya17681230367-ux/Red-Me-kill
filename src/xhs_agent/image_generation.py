from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from .config import ImageGenerationSettings
from .repository import Repository


TARGET_ACCOUNTS = {
    "business_a": "论文/作业业务号",
    "business_b": "考试/挂科补救业务号",
    "business_c": "案例/转化业务号",
}


@dataclass(frozen=True)
class ImageNodeResult:
    created_jobs: int
    completed_jobs: int
    failed_jobs: int


class ImageGenerationClient:
    def __init__(self, settings: ImageGenerationSettings):
        self.settings = settings

    def enabled(self) -> bool:
        return bool(self.settings.enabled and self.settings.base_url and self.settings.api_key and self.settings.model)

    def generate(self, prompt: str) -> dict:
        if not self.enabled():
            raise RuntimeError("图片生成 API 未配置，已保留任务等待后续执行。")
        payload = {
            "model": self.settings.model,
            "prompt": prompt,
        }
        if self.settings.provider.lower() == "siliconflow":
            payload.update({"image_size": "1024x1024", "batch_size": 1})
        else:
            payload.update({"size": "1024x1024", "n": 1})
        response = httpx.post(
            f"{self.settings.base_url.rstrip('/')}/images/generations",
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.settings.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()


def run_image_generation_node(repo: Repository, settings: ImageGenerationSettings, limit: int | None = None) -> ImageNodeResult:
    created = enqueue_image_jobs(repo, limit)
    client = ImageGenerationClient(settings)
    if not client.enabled():
        return ImageNodeResult(created_jobs=created, completed_jobs=0, failed_jobs=0)

    completed = 0
    failed = 0
    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for job in repo.pending_image_jobs(limit):
        job_id = int(job["job_id"])
        repo.mark_image_job_running(job_id, settings.provider, settings.model)
        try:
            payload = client.generate(job["prompt"])
            image_url, image_path = _store_image_payload(payload, output_dir, job_id)
            repo.add_generated_image(
                job_id=job_id,
                note_id=job["note_id"],
                target_account=job["target_account"],
                prompt=job["prompt"],
                image_url=image_url,
                image_path=image_path,
            )
            completed += 1
        except Exception as exc:
            repo.mark_image_job_failed(job_id, str(exc))
            failed += 1
    return ImageNodeResult(created_jobs=created, completed_jobs=completed, failed_jobs=failed)


def enqueue_image_jobs(repo: Repository, limit: int | None = None) -> int:
    notes = repo.query(
        """
        select *
        from note_metrics
        where title is not null
          and title != ''
          and title != '待抓取标题'
        order by (likes + collects + comments + shares + leads * 5) desc, captured_at desc
        """
    )
    if limit:
        notes = notes[:limit]

    created = 0
    for row in notes:
        for account_key, account_name in TARGET_ACCOUNTS.items():
            if _image_job_exists(repo, row["note_id"], account_key):
                continue
            repo.add_image_job(row["note_id"], account_key, _cover_prompt(row, account_name))
            created += 1
    return created


def _image_job_exists(repo: Repository, note_id: str, target_account: str) -> bool:
    rows = repo.query(
        """
        select job_id
        from image_jobs
        where note_id = ? and target_account = ?
        limit 1
        """,
        (note_id, target_account),
    )
    return bool(rows)


def _cover_prompt(row, account_name: str) -> str:
    title = row["title"] or "留学生课业痛点"
    body = (row["body"] or "")[:600]
    topic = _topic_from_text(title + body)
    return (
        "生成一张小红书封面图，适合教育/留学生课业服务账号使用。"
        f"目标账号：{account_name}。"
        f"参考爆贴标题：{title}。"
        f"主题方向：{topic}。"
        "画面要求：真实、清爽、有学习场景，避免夸张营销和侵权元素；"
        "封面需要留出大标题区域，适合叠加中文短标题；"
        "风格参考小红书知识分享封面，明亮但不花哨。"
    )


def _topic_from_text(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in ("dissertation", "proposal", "论文", "导师", "essay")):
        return "论文/作业推进"
    if any(word in lower for word in ("appeal", "挂科", "出分", "申诉")):
        return "挂科补救/申诉"
    if any(word in lower for word in ("exam", "quiz", "final", "考试", "暑课")):
        return "考试周/暑课自救"
    if any(word in lower for word in ("turnitin", "查重", "降ai")):
        return "查重和 AI 率焦虑"
    return "留学生课业压力共鸣"


def _store_image_payload(payload: dict, output_dir: Path, job_id: int) -> tuple[str, str]:
    data = payload.get("data") or []
    if not data:
        raise RuntimeError(f"图片 API 未返回图片数据：{payload}")
    item = data[0]
    if item.get("url"):
        return str(item["url"]), ""
    b64_json = item.get("b64_json")
    if not b64_json:
        raise RuntimeError(f"图片 API 返回格式不支持：{payload}")
    image_bytes = base64.b64decode(re.sub(r"^data:image/[^;]+;base64,", "", b64_json))
    path = output_dir / f"image-job-{job_id}.png"
    path.write_bytes(image_bytes)
    return "", str(path)
