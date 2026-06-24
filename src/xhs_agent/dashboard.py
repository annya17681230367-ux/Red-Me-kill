from __future__ import annotations

import html
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
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
            if self.path.startswith("/api/skills"):
                _send_json(self, _skills_payload(settings))
                return
            if self.path.startswith("/api/hotspots"):
                _send_json(self, _hotspots_payload(repo))
                return
            if self.path.startswith("/api/daily-report"):
                _send_json(self, _daily_report_payload(repo, settings))
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

    server = HTTPServer((host, port), DashboardHandler)
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


def _skills_payload(settings) -> list[dict]:
    return [
        {"name": "DeepSeek Analysis", "status": "connected", "usage": "爆贴分析、日报、标题/封面/私信建议"},
        {"name": "Claude Skill Node", "status": "reserved", "usage": "高级内容生成、视觉结构、长文本策略"},
        {"name": "Auto-Redbook-Skills", "status": "reserved", "usage": "小红书内容生产流程，发布前人工审核"},
        {"name": "guizang-social-card-skill", "status": "reserved", "usage": "小红书图文卡片、封面、轮播图生成"},
        {"name": "Social Assistant Input", "status": "reserved", "usage": "社媒助手自动推送小红书链接"},
        {
            "name": "Image API",
            "status": "connected" if settings.image_generation.enabled else "pending_key",
            "usage": "真实出图/改图",
        },
    ]


def _hotspots_payload(repo: Repository) -> list[dict]:
    rows = repo.query(
        """
        select title, likes, collects, comments, shares, leads
        from note_metrics
        where title is not null and title != '' and title != '待抓取标题'
        order by (likes + collects + comments + shares + leads * 5) desc, captured_at desc
        limit 8
        """
    )
    if rows:
        return [
            {
                "topic": row["title"],
                "score": int(row["likes"] or 0)
                + int(row["collects"] or 0)
                + int(row["comments"] or 0)
                + int(row["shares"] or 0)
                + int(row["leads"] or 0) * 5,
            }
            for row in rows
        ]
    return [
        {"topic": "dissertation proposal 卡住", "score": 92},
        {"topic": "Turnitin AI 率突然升高", "score": 88},
        {"topic": "英国挂科 appeal 证据链", "score": 86},
        {"topic": "暑课 final 一周自救", "score": 83},
        {"topic": "导师不回 follow-up 邮件", "score": 81},
        {"topic": "新生选课避坑", "score": 78},
    ]


def _daily_report_payload(repo: Repository, settings) -> dict:
    reports = _latest_files(Path(settings.agent.reports_dir), ("daily-*.html", "daily-*.pdf", "daily-*.md"), 3)
    return {
        "notes": _scalar(repo, "select count(*) from note_metrics"),
        "latest_reports": [item[0].name for item in reports],
        "recommendation": "优先生产 proposal、Turnitin、appeal 三类高转化内容。",
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
  <title>小红书数据运营 Agent 看板</title>
  <style>
    :root {{ --bg:#f5f7fb; --panel:#fff; --ink:#101828; --muted:#667085; --line:#d9e2ec; --red:#e94162; --green:#16875a; --gold:#9a6a14; --nav:#111827; --nav2:#1f2937; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,"PingFang SC","Microsoft YaHei",sans-serif; }}
    .shell {{ display:grid; grid-template-columns:246px minmax(0,1fr); min-height:100vh; }}
    aside {{ background:linear-gradient(180deg,var(--nav),var(--nav2)); color:#fff; padding:22px 16px; position:sticky; top:0; height:100vh; }}
    .brand {{ font-size:21px; font-weight:800; margin-bottom:6px; }}
    .sub {{ color:#b8c0cc; font-size:12px; margin-bottom:20px; }}
    nav a {{ display:block; color:#d5d9e2; text-decoration:none; padding:10px 12px; border-radius:8px; margin:3px 0; font-size:14px; }}
    nav a:hover, nav a.active {{ background:#344054; color:white; }}
    main {{ padding:24px 30px 42px; display:grid; gap:18px; }}
    .top {{ display:flex; justify-content:space-between; align-items:flex-start; gap:18px; }}
    h1 {{ margin:0; font-size:30px; letter-spacing:0; }}
    h2 {{ margin:0 0 14px; font-size:19px; }}
    h3 {{ margin:0 0 8px; font-size:15px; }}
    .muted {{ color:var(--muted); font-size:13px; }}
    .status {{ display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end; }}
    .pill {{ display:inline-flex; align-items:center; border:1px solid var(--line); border-radius:999px; padding:5px 10px; font-size:12px; background:#fff; color:#475467; }}
    .ok {{ background:#eaf7ef; color:var(--green); border-color:#bde4cc; }}
    .warn {{ background:#fff7e8; color:var(--gold); border-color:#f3d4a6; }}
    .danger {{ background:#fff0f4; color:var(--red); border-color:#f5c4d0; }}
    .grid4 {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }}
    .grid3 {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }}
    .two {{ display:grid; grid-template-columns:1.25fr .75fr; gap:12px; }}
    .card,.section {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; box-shadow:0 1px 2px rgba(16,24,40,.04); }}
    .card {{ padding:15px; }}
    .metric .label {{ color:var(--muted); font-size:13px; }}
    .metric strong {{ display:block; font-size:28px; margin:7px 0 2px; }}
    .metric .delta {{ font-size:12px; color:var(--green); }}
    .section {{ padding:18px; }}
    .toolbar {{ display:flex; justify-content:space-between; gap:10px; align-items:center; margin-bottom:12px; }}
    .btn {{ display:inline-flex; align-items:center; gap:6px; border:0; background:#172033; color:white; text-decoration:none; border-radius:7px; padding:8px 11px; font-weight:700; font-size:13px; }}
    .btn.secondary {{ background:#eef2f7; color:#344054; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; background:white; }}
    th,td {{ border-bottom:1px solid var(--line); padding:10px; text-align:left; vertical-align:top; }}
    th {{ background:#f8fafc; color:#475467; font-weight:700; }}
    .score {{ font-weight:800; color:var(--red); }}
    .case {{ border:1px solid var(--line); border-radius:9px; padding:13px; background:#fff; }}
    .case p {{ margin:7px 0; color:#475467; font-size:13px; line-height:1.55; }}
    .empty {{ border:1px dashed #aeb9c7; background:#fbfcfe; border-radius:9px; padding:14px; color:#667085; font-size:13px; }}
    .node {{ display:grid; grid-template-columns:155px 90px 1fr; gap:10px; align-items:start; border-bottom:1px solid var(--line); padding:11px 0; }}
    .node:last-child {{ border-bottom:0; }}
    .mono {{ font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; background:#f1f4f8; border:1px solid #d9e2ec; border-radius:7px; padding:10px; font-size:12px; white-space:pre-wrap; }}
    .tag {{ display:inline-block; border-radius:999px; padding:3px 8px; font-size:12px; background:#eef7f8; color:#0f7b83; margin:2px; }}
    .tag.red {{ background:#fff0f4; color:var(--red); }}
    form {{ display:flex; gap:8px; flex-wrap:wrap; }}
    input {{ height:38px; border:1px solid var(--line); border-radius:6px; padding:0 10px; min-width:260px; flex:1; }}
    button {{ height:38px; border:0; border-radius:6px; padding:0 14px; background:var(--red); color:white; font-weight:700; cursor:pointer; }}
    @media(max-width:1050px) {{ .shell {{ grid-template-columns:1fr; }} aside {{ position:relative; height:auto; }} .grid4,.grid3,.two {{ grid-template-columns:1fr; }} .status {{ justify-content:flex-start; }} }}
  </style>
</head>
<body>
<div class="shell">
  <aside>
    <div class="brand">XHS Ops Agent</div>
    <div class="sub">小红书数据运营系统</div>
    <nav>
      <a class="active" href="#overview">总览</a><a href="#accounts">账号看板</a><a href="#hotspots">爆贴库</a><a href="#structure">爆贴拆解</a><a href="#reports">日报周报</a><a href="#content">内容生成</a><a href="#image">图片生成</a><a href="#skills">Skill 接口</a><a href="#social">社媒助手</a><a href="#testing">测试反馈</a>
    </nav>
  </aside>
  <main>
    <header class="top">
      <div><h1>小红书数据运营 Agent 看板</h1><div class="muted">云端运行 · DeepSeek 分析已接入 · Claude / 图片 / 社媒助手接口已预留</div></div>
      <div class="status"><span class="pill ok">Cloud Running</span><span class="pill ok">{html.escape(settings.llm.provider)} / {html.escape(settings.llm.model)}</span><span class="pill warn">Claude Reserved</span><span class="pill {'ok' if settings.image_generation.enabled else 'danger'}">{'Image API Connected' if settings.image_generation.enabled else 'Image API Pending'}</span></div>
    </header>

    <section id="overview" class="grid4">
      <div class="card metric"><div class="label">爆贴数据</div><strong>{stats['notes'] or 6}</strong><div class="delta">真实数据 + 演示占位</div></div>
      <div class="card metric"><div class="label">社媒输入</div><strong>{stats['links']}</strong><div class="delta">接口已预留</div></div>
      <div class="card metric"><div class="label">图片任务</div><strong>{stats['image_jobs'] or 18}</strong><div class="delta">6 选题 × 3 账号</div></div>
      <div class="card metric"><div class="label">模型调用</div><strong>{stats['model_calls']}</strong><div class="delta">Token 成本可追踪</div></div>
    </section>

    <section id="accounts" class="section"><div class="toolbar"><h2>账号数据看板</h2><span class="muted">后续接真实账号 API 后自动更新</span></div>{_account_table()}</section>

    <section id="hotspots" class="section"><div class="toolbar"><h2>爆贴库：留学生营销日历课业服务</h2><a class="btn secondary" href="/api/hotspots" target="_blank">查看接口</a></div>{_hotspot_table(notes)}</section>

    <section id="structure" class="section"><h2>爆贴结构拆解</h2><div class="grid3">{_structure_cards()}</div></section>

    <section id="reports" class="section"><div class="toolbar"><h2>日报/周报产出</h2><a class="btn secondary" href="/api/daily-report" target="_blank">日报接口</a></div><div class="two"><div>{_daily_report_table()}</div><div>{_report_files_table(reports)}</div></div></section>

    <section id="content" class="section"><h2>内容生成节点</h2><div class="two"><div class="case"><h3>输入</h3><p>爆贴：Turnitin AI 率突然升高</p><p>账号：案例/转化业务号</p><p>营销节点：7月初稿查重期</p></div><div class="case"><h3>DeepSeek 输出</h3><p>标题：AI率爆了先别重写，先查这4项</p><p>正文：情绪安抚 → 检查清单 → 修改顺序 → 私信初筛</p><p>评论引导：发截图帮你判断先改哪一块。</p></div></div></section>

    <section id="image" class="section"><h2>图片生成节点</h2>{_image_node_block(settings, image_jobs)}</section>

    <section id="skills" class="section"><div class="toolbar"><h2>Skill 接口中心</h2><a class="btn secondary" href="/api/skills" target="_blank">Skill JSON</a></div><div class="grid3">{_skill_cards(settings)}</div></section>

    <section id="social" class="section"><h2>社媒助手输入接口</h2><div class="two"><div><p class="muted">后续社媒助手调用接口后，小红书链接会进入 Agent 数据库。</p><form method="post" action="/api/social-links"><input name="url" placeholder="粘贴小红书链接"><input name="sender_name" value="social-assistant"><button type="submit">写入</button></form></div><div class="mono">POST /api/social-links\nContent-Type: application/json\n\n{{"url":"https://www.xiaohongshu.com/explore/xxx","sender_name":"social-assistant"}}</div></div></section>

    <section id="testing" class="section"><h2>测试反馈</h2><div class="empty">3 人 3 天测试记录、真实 Bug、第一次路演反馈修改记录将在这里沉淀。当前已准备模板，待测试人开始使用后填入。</div></section>
  </main>
</div>
</body>
</html>"""

def _account_table() -> str:
    rows = [
        ("业务号 A", "论文/作业服务", 126, 214, "+69.8%", "追 proposal、导师不回、DDL 倒排内容。"),
        ("业务号 B", "考试/挂科补救", 88, 147, "+67.0%", "追 appeal、暑课 final、补考准备内容。"),
        ("业务号 C", "案例/转化承接", 53, 92, "+73.6%", "追 Turnitin、AI 率、真实案例拆解内容。"),
    ]
    body = "".join(
        f"<tr><td>{name}</td><td>{position}</td><td>{old}</td><td>{new}</td><td class='score'>{delta}</td><td>{action}</td></tr>"
        for name, position, old, new, delta, action in rows
    )
    return "<table><tr><th>账号</th><th>定位</th><th>昨日互动</th><th>今日互动</th><th>变化</th><th>今日动作</th></tr>" + body + "</table>"


def _hotspot_table(notes) -> str:
    if notes:
        body = "".join(_hotspot_row(row) for row in notes)
    else:
        demos = [
            ("dissertation proposal 卡住", "6月下旬 proposal / 暑课", 92, "论文/作业业务号", "私信收专业、DDL、学校要求。"),
            ("Turnitin AI 率突然升高", "7月初查重/初稿", 88, "案例/转化业务号", "引导截图初筛。"),
            ("英国挂科 appeal 证据链", "出分/补考窗口", 86, "考试/挂科补救业务号", "收成绩单、学校邮件、申诉 DDL。"),
            ("暑课 final 一周自救", "暑课考试周", 83, "考试/挂科补救业务号", "按科目给复习规划。"),
            ("导师不回 follow-up 邮件", "论文阶段", 81, "论文/作业业务号", "提供邮件模板和时间线。"),
            ("新生选课避坑", "开学前", 78, "案例/转化业务号", "收专业和课程清单。"),
        ]
        body = "".join(
            f"<tr><td>{topic}</td><td>{calendar}</td><td class='score'>{score}</td><td>{account}</td><td>{action}</td></tr>"
            for topic, calendar, score, account, action in demos
        )
    return "<table><tr><th>爆贴主题</th><th>营销节点</th><th>爆点分</th><th>适配账号</th><th>转化动作</th></tr>" + body + "</table>"


def _hotspot_row(row) -> str:
    title = html.escape(row["title"] or "")
    score = int(row["likes"] or 0) + int(row["collects"] or 0) + int(row["comments"] or 0) + int(row["shares"] or 0) + int(row["leads"] or 0) * 5
    return f"<tr><td>{title}</td><td>自动识别</td><td class='score'>{score}</td><td>{_target_account_for_title(title)}</td><td>拆标题、封面和私信承接。</td></tr>"


def _target_account_for_title(title: str) -> str:
    text = title.lower()
    if any(word in text for word in ("appeal", "挂科", "final", "考试", "补考")):
        return "考试/挂科补救业务号"
    if any(word in text for word in ("turnitin", "ai", "案例")):
        return "案例/转化业务号"
    return "论文/作业业务号"


def _structure_cards() -> str:
    cases = [
        ("Proposal 卡住", "痛点共鸣 → 3步自救 → 避坑清单 → 私信承接", "英国 proposal 卡住？3步自救 + 导师不回模板"),
        ("AI 率升高", "情绪安抚 → 4项检查 → 修改顺序 → 截图初筛", "AI率爆了先别重写，先查这4项"),
        ("Appeal", "常见误区 → 证据链 → 时间线 → 邮件措辞", "Appeal 不是写惨，证据链才是关键"),
        ("暑课 Final", "科目分类 → 优先级 → 7日计划 → 资料整理", "暑课 final 只剩7天，先救这3类题"),
        ("导师不回", "场景判断 → 邮件模板 → 发送时间 → 后续动作", "导师不回？这封 follow-up 更稳"),
        ("选课避坑", "课程风险 → 作业比例 → 老师评分 → 清单保存", "新生选课别只看名字，先查这5点"),
    ]
    return "".join(
        f"<div class='case'><h3>{name}</h3><p><span class='tag'>结构</span> {structure}</p><p><span class='tag red'>标题</span> {title}</p></div>"
        for name, structure, title in cases
    )


def _daily_report_table() -> str:
    return (
        "<table><tr><th>模块</th><th>今日结论</th><th>下一步动作</th></tr>"
        "<tr><td>数据总览</td><td>收录课业服务爆贴，账号互动增长。</td><td>优先复用 proposal、AI率、appeal 三类内容。</td></tr>"
        "<tr><td>爆贴共性</td><td>强痛点 + 明确时间压力 + 可私信诊断，更容易转化。</td><td>封面统一用“问题 + 步骤 + 清单”。</td></tr>"
        "<tr><td>内容建议</td><td>论文号做 proposal，考试号做 appeal/final，案例号做 Turnitin。</td><td>每天每号至少 1 条选题进入排期。</td></tr>"
        "</table>"
    )


def _report_files_table(reports) -> str:
    if not reports:
        return "<div class='empty'><b>历史报告占位</b><br>后续展示 daily-YYYY-MM-DD.html、weekly-YYYY-MM-DD.pdf，并支持点击下载。</div>"
    return "<table><tr><th>文件</th><th>更新时间</th><th>大小</th></tr>" + "".join(_file_row(item) for item in reports) + "</table>"


def _image_node_block(settings, image_jobs) -> str:
    rows = "".join(_image_job_row(row) for row in image_jobs)
    job_table = "<table><tr><th>ID</th><th>目标账号</th><th>状态</th><th>模型</th></tr>" + (rows or "<tr><td colspan='4'>暂无真实图片任务，已保留节点模板。</td></tr>") + "</table>"
    api_status = "已配置" if settings.image_generation.enabled else "待填 Key"
    return (
        "<div class='node'><b>Claude 图片结构</b><span class='pill warn'>预留</span><div>输入爆贴标题、账号定位、营销节点；输出封面标题、副标题、画面元素和图片 Prompt。</div></div>"
        "<div class='node'><b>guizang 卡片 Skill</b><span class='pill warn'>预留</span><div>把内容结构渲染成小红书图文卡片、轮播图或封面模板。</div></div>"
        f"<div class='node'><b>Image API</b><span class='pill danger'>{api_status}</span><div>配置图片 API 后，图片任务会从 Prompt 变成真实封面图。</div></div>"
        "<div class='mono'>示例 Prompt：小红书知识卡片封面，标题“AI率爆了先别重写”，电脑查重报告、红色风险提示、4步检查清单，清爽留学生学习场景。</div>"
        "<h3 style='margin-top:14px'>图片任务队列</h3>"
        + job_table
    )


def _skill_cards(settings) -> str:
    image_status = "已配置" if settings.image_generation.enabled else "待配置"
    skills = [
        ("DeepSeek Analysis", "已接入", "ok", "爆贴分析、日报、标题/封面/私信建议。"),
        ("Claude Skill Node", "预留", "warn", "高级内容生成、视觉结构、长文本策略。"),
        ("Auto-Redbook-Skills", "预留", "warn", "小红书内容生产流程，发布前人工审核。"),
        ("guizang-social-card-skill", "预留", "warn", "小红书图文卡片、封面、轮播图生成。"),
        ("Social Assistant Input", "预留", "warn", "社媒助手自动推送小红书链接。"),
        ("Image API", image_status, "danger" if not settings.image_generation.enabled else "ok", "接入后图片任务变成真实出图。"),
    ]
    return "".join(
        f"<div class='case'><h3>{name}</h3><span class='pill {klass}'>{status}</span><p>{desc}</p></div>"
        for name, status, klass, desc in skills
    )


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
