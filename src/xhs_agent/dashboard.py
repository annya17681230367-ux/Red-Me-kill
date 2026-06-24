from __future__ import annotations

import html
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from .models import FeishuLink
from .repository import Repository


def run_dashboard(repo: Repository, settings, host: str = "0.0.0.0", port: int = 8000) -> None:
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path.startswith("/api/status"):
                _send_json(self, _status_payload(repo, settings))
                return
            if self.path.startswith("/health"):
                _send_text(self, "ok")
                return
            _send_html(self, _render_dashboard(repo, settings))

        def do_POST(self) -> None:  # noqa: N802
            if self.path.startswith("/api/social-links"):
                payload = _read_payload(self)
                url = str(payload.get("url") or "").strip()
                sender_name = str(payload.get("sender_name") or "social-assistant").strip()
                if not url:
                    _send_json(self, {"ok": False, "error": "missing url"}, status=400)
                    return
                link = FeishuLink(
                    message_id=f"social-{datetime.now().timestamp()}-{url}",
                    sender_name=sender_name,
                    sent_at=datetime.now(),
                    url=url,
                )
                added = repo.add_links([link])
                _send_json(self, {"ok": True, "added": added, "url": url})
                return
            _send_json(self, {"ok": False, "error": "not found"}, status=404)

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"看板已启动：http://{host}:{port}")
    server.serve_forever()


def _read_payload(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    raw = handler.rfile.read(length).decode("utf-8", errors="ignore")
    content_type = handler.headers.get("Content-Type") or ""
    if "application/json" in content_type:
        return json.loads(raw or "{}")
    parsed = parse_qs(raw)
    return {key: values[-1] for key, values in parsed.items()}


def _status_payload(repo: Repository, settings) -> dict:
    return {
        "notes": _scalar(repo, "select count(*) from note_metrics"),
        "links": _scalar(repo, "select count(*) from feishu_links"),
        "image_jobs": _scalar(repo, "select count(*) from image_jobs"),
        "generated_images": _scalar(repo, "select count(*) from generated_images"),
        "model_calls": _scalar(repo, "select count(*) from model_call_logs"),
        "llm_provider": settings.llm.provider,
        "llm_model": settings.llm.model,
        "claude_skill_node": "reserved" if settings.llm.provider != "anthropic" else "enabled",
    }


def _render_dashboard(repo: Repository, settings) -> str:
    stats = _status_payload(repo, settings)
    notes = repo.query(
        """
        select note_id, title, body, likes, collects, comments, shares, views, leads
        from note_metrics
        where title is not null and title != '' and title != '待抓取标题'
        order by (likes + collects + comments + shares + leads * 5) desc, captured_at desc
        limit 8
        """
    )
    reports = _latest_files(Path(settings.agent.reports_dir), ("*.html", "*.pdf", "*.md"), 8)
    calls = repo.query(
        """
        select task_type, provider, model, input_tokens, output_tokens, total_tokens,
               estimated_cost_usd, status, created_at
        from model_call_logs
        order by log_id desc
        limit 6
        """
    )
    image_jobs = repo.query(
        """
        select job_id, note_id, target_account, status, provider, model, error, created_at
        from image_jobs
        order by job_id desc
        limit 8
        """
    )
    generated = repo.query(
        """
        select target_account, note_id, image_url, image_path, created_at
        from generated_images
        order by image_id desc
        limit 6
        """
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>小红书运营 AI 看板</title>
  <style>
    :root {{
      color-scheme: light;
      --ink:#172033; --muted:#667085; --line:#d9e0ea; --soft:#f6f8fb;
      --red:#e94162; --teal:#0f7b83; --green:#148a4a; --gold:#9a6a14;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:#fff; }}
    header {{ padding:22px 28px; border-bottom:1px solid var(--line); display:flex; justify-content:space-between; gap:16px; align-items:flex-end; }}
    h1 {{ margin:0; font-size:28px; letter-spacing:0; }}
    h2 {{ margin:0 0 14px; font-size:18px; }}
    main {{ padding:24px 28px 36px; display:grid; gap:20px; }}
    .status {{ color:var(--muted); font-size:14px; }}
    .grid {{ display:grid; grid-template-columns:repeat(5,minmax(120px,1fr)); gap:12px; }}
    .metric {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:var(--soft); }}
    .metric strong {{ display:block; font-size:26px; margin-top:8px; }}
    .band {{ border-top:1px solid var(--line); padding-top:20px; }}
    .cols {{ display:grid; grid-template-columns:1.5fr 1fr; gap:18px; }}
    .cards {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }}
    .card {{ border:1px solid var(--line); border-radius:8px; padding:14px; min-height:150px; }}
    .card h3 {{ margin:0 0 10px; font-size:16px; line-height:1.4; }}
    .muted {{ color:var(--muted); font-size:13px; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th,td {{ border-bottom:1px solid var(--line); padding:9px 8px; text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-weight:600; background:var(--soft); }}
    .pill {{ display:inline-block; padding:3px 8px; border-radius:999px; background:#eef7f8; color:var(--teal); font-size:12px; }}
    .warn {{ background:#fff7e8; color:var(--gold); }}
    .ok {{ background:#eaf7ef; color:var(--green); }}
    form {{ display:flex; gap:8px; flex-wrap:wrap; }}
    input {{ height:38px; border:1px solid var(--line); border-radius:6px; padding:0 10px; min-width:280px; flex:1; }}
    button {{ height:38px; border:0; border-radius:6px; padding:0 14px; background:var(--red); color:white; font-weight:700; cursor:pointer; }}
    pre {{ white-space:pre-wrap; word-break:break-word; background:var(--soft); border:1px solid var(--line); border-radius:8px; padding:12px; font-size:12px; }}
    @media (max-width: 900px) {{ .grid,.cards,.cols {{ grid-template-columns:1fr; }} header {{ display:block; }} }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>小红书运营 AI 看板</h1>
      <div class="status">云端运行中 · 主模型 {html.escape(settings.llm.provider)} / {html.escape(settings.llm.model)}</div>
    </div>
    <div class="status">更新时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
  </header>
  <main>
    <section class="grid">
      {_metric("爆贴数据", stats["notes"])}
      {_metric("社媒输入", stats["links"])}
      {_metric("图片任务", stats["image_jobs"])}
      {_metric("生成图片", stats["generated_images"])}
      {_metric("模型调用", stats["model_calls"])}
    </section>

    <section class="band cols">
      <div>
        <h2>生成内容演示案例</h2>
        <div class="cards">{''.join(_note_card(row) for row in notes) or '<p class="muted">还没有爆贴数据。先运行 seed-demo 或接入社媒助手链接。</p>'}</div>
      </div>
      <div>
        <h2>社媒助手输入接口</h2>
        <form method="post" action="/api/social-links">
          <input name="url" placeholder="粘贴小红书链接，后续社媒助手也会调用这里">
          <input name="sender_name" value="social-assistant" aria-label="sender">
          <button type="submit">写入</button>
        </form>
        <pre>POST /api/social-links
Content-Type: application/json

{{"url":"https://www.xiaohongshu.com/explore/xxx","sender_name":"social-assistant"}}</pre>
      </div>
    </section>

    <section class="band">
      <h2>日报/周报产物</h2>
      <table><thead><tr><th>文件</th><th>更新时间</th><th>大小</th></tr></thead><tbody>{''.join(_file_row(item) for item in reports) or '<tr><td colspan="3">暂无报告文件</td></tr>'}</tbody></table>
    </section>

    <section class="band cols">
      <div>
        <h2>模型 Token 与费用</h2>
        <table><thead><tr><th>任务</th><th>模型</th><th>Token</th><th>费用</th><th>状态</th></tr></thead><tbody>{''.join(_call_row(row) for row in calls) or '<tr><td colspan="5">暂无模型调用</td></tr>'}</tbody></table>
      </div>
      <div>
        <h2>Claude Skill 节点</h2>
        {_claude_status(settings)}
      </div>
    </section>

    <section class="band cols">
      <div>
        <h2>图片生成节点</h2>
        <table><thead><tr><th>ID</th><th>目标账号</th><th>状态</th><th>模型</th></tr></thead><tbody>{''.join(_image_job_row(row) for row in image_jobs) or '<tr><td colspan="4">暂无图片任务</td></tr>'}</tbody></table>
      </div>
      <div>
        <h2>已生成图片</h2>
        <table><thead><tr><th>目标账号</th><th>来源笔记</th><th>图片</th></tr></thead><tbody>{''.join(_generated_row(row) for row in generated) or '<tr><td colspan="3">暂无生成图片</td></tr>'}</tbody></table>
      </div>
    </section>
  </main>
</body>
</html>"""


def _metric(label: str, value) -> str:
    return f'<div class="metric"><span class="muted">{html.escape(label)}</span><strong>{value}</strong></div>'


def _note_card(row) -> str:
    title = html.escape(row["title"] or "")
    body = html.escape((row["body"] or "")[:110])
    score = int(row["likes"] or 0) + int(row["collects"] or 0) + int(row["comments"] or 0) + int(row["shares"] or 0) + int(row["leads"] or 0) * 5
    return (
        '<article class="card">'
        f"<h3>{title}</h3>"
        f'<p class="muted">{body}</p>'
        f'<span class="pill">爆贴分 {score}</span> '
        f'<span class="pill warn">内容方向：标题/封面/私信承接</span>'
        "</article>"
    )


def _file_row(item: tuple[Path, float, int]) -> str:
    path, mtime, size = item
    return (
        "<tr>"
        f"<td>{html.escape(path.name)}</td>"
        f"<td>{datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')}</td>"
        f"<td>{round(size / 1024, 1)} KB</td>"
        "</tr>"
    )


def _call_row(row) -> str:
    token_text = f"{row['input_tokens']} / {row['output_tokens']} / {row['total_tokens']}"
    return (
        "<tr>"
        f"<td>{html.escape(row['task_type'])}</td>"
        f"<td>{html.escape(row['provider'])}<br><span class='muted'>{html.escape(row['model'])}</span></td>"
        f"<td>{token_text}</td>"
        f"<td>${float(row['estimated_cost_usd'] or 0):.6f}</td>"
        f"<td><span class='pill ok'>{html.escape(row['status'])}</span></td>"
        "</tr>"
    )


def _image_job_row(row) -> str:
    model = " / ".join(part for part in (row["provider"], row["model"]) if part) or "待配置"
    return (
        "<tr>"
        f"<td>{row['job_id']}</td>"
        f"<td>{html.escape(row['target_account'])}</td>"
        f"<td>{html.escape(row['status'])}</td>"
        f"<td>{html.escape(model)}</td>"
        "</tr>"
    )


def _generated_row(row) -> str:
    link = row["image_url"] or row["image_path"] or ""
    return (
        "<tr>"
        f"<td>{html.escape(row['target_account'])}</td>"
        f"<td>{html.escape(row['note_id'])}</td>"
        f"<td>{html.escape(link or '已记录')}</td>"
        "</tr>"
    )


def _claude_status(settings) -> str:
    if settings.llm.provider == "anthropic" and settings.llm.api_key:
        return '<p><span class="pill ok">已启用</span></p><p class="muted">当前模型会通过 Anthropic/Claude 通道运行。</p>'
    return (
        '<p><span class="pill warn">已预留，待 Claude Key 开启</span></p>'
        '<p class="muted">当前长期主模型是 DeepSeek。Claude skill 节点已作为高级内容生成/策略节点预留，后续填入 Claude API Key 后切换 provider=anthropic 即可启用。</p>'
    )


def _latest_files(directory: Path, patterns: tuple[str, ...], limit: int) -> list[tuple[Path, float, int]]:
    if not directory.exists():
        return []
    files: list[Path] = []
    for pattern in patterns:
        files.extend(directory.glob(pattern))
    return sorted(
        [(path, path.stat().st_mtime, path.stat().st_size) for path in files],
        key=lambda item: item[1],
        reverse=True,
    )[:limit]


def _scalar(repo: Repository, sql: str):
    return repo.query(sql)[0][0]


def _send_html(handler: BaseHTTPRequestHandler, body: str, status: int = 200) -> None:
    _send_bytes(handler, body.encode("utf-8"), "text/html; charset=utf-8", status)


def _send_json(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    _send_bytes(handler, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", status)


def _send_text(handler: BaseHTTPRequestHandler, body: str, status: int = 200) -> None:
    _send_bytes(handler, body.encode("utf-8"), "text/plain; charset=utf-8", status)


def _send_bytes(handler: BaseHTTPRequestHandler, body: bytes, content_type: str, status: int) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
