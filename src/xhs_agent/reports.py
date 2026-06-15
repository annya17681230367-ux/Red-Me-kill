from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import markdown
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .analysis import XhsAnalyzer
from .repository import Repository
from .xhs_hotspots import load_daily_hotspots


@dataclass(frozen=True)
class ReportResult:
    markdown_path: Path
    html_path: Path
    pdf_path: Path
    feishu_summary: str


class ReportBuilder:
    def __init__(self, repo: Repository, analyzer: XhsAnalyzer, reports_dir: str):
        self.repo = repo
        self.analyzer = analyzer
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def build_daily(self, report_date: date | None = None) -> ReportResult:
        day = report_date or datetime.now().date()
        start = day.isoformat()
        end = (day + timedelta(days=1)).isoformat()
        notes = _dedupe_notes(
            self.repo.query(
                """
                select *
                from note_metrics
                where substr(coalesce(published_at, captured_at), 1, 10) >= ?
                  and substr(coalesce(published_at, captured_at), 1, 10) < ?
                  and not (
                    title = '待抓取标题'
                    and exists (
                      select 1
                      from note_metrics real_note
                      where real_note.url = note_metrics.url
                        and real_note.title is not null
                        and real_note.title != ''
                        and real_note.title != '待抓取标题'
                    )
                  )
                order by captured_at desc
                """,
                (start, end),
            )
        )
        md = [
            f"# 小红书账号日报 {day.isoformat()}",
            "",
            "## 今日数据总览",
            "",
            f"- 今日收录笔记：{len(notes)} 条",
            f"- 今日总互动：{sum(r['likes'] + r['collects'] + r['comments'] + r['shares'] for r in notes)}",
            f"- 今日私信/线索：{sum(r['leads'] for r in notes)}",
            "",
            "## 今日爆贴数据",
        ]
        md.extend(_viral_section(notes, "今日"))
        md.extend(_viral_analysis_section(notes))
        md.extend(_monthly_marketing_section(day))
        md.extend(_hotspot_section(load_daily_hotspots(day)))
        md.extend(
            [
                "",
            "## 今日帖子修改策略表",
            ]
        )
        md.extend(_daily_strategy_table(notes, self.analyzer))
        if not notes:
            md.append("今日还没有收录到小红书链接或 API 数据。请确认群链接格式和微信复制入口。")
        return self._write("daily", day, md, f"小红书日报 {day.isoformat()}：收录 {len(notes)} 条笔记。")

    def build_weekly(self, report_date: date | None = None) -> ReportResult:
        day = report_date or datetime.now().date()
        start_day = day - timedelta(days=6)
        start = start_day.isoformat()
        end = (day + timedelta(days=1)).isoformat()
        notes = _dedupe_notes(
            self.repo.query(
            """
            select *
            from note_metrics
            where substr(coalesce(published_at, captured_at), 1, 10) >= ?
              and substr(coalesce(published_at, captured_at), 1, 10) < ?
              and not (
                title = '待抓取标题'
                and exists (
                  select 1
                  from note_metrics real_note
                  where real_note.url = note_metrics.url
                    and real_note.title is not null
                    and real_note.title != ''
                    and real_note.title != '待抓取标题'
                )
              )
            order by (likes + collects + comments + shares + leads * 5) desc
            """,
            (start, end),
            )
        )
        accounts = self.repo.query(
            """
            select a.account_id, a.account_name, a.operator, a.niche,
                   min(s.followers) as followers_start,
                   max(s.followers) as followers_end,
                   min(s.notes_count) as notes_start,
                   max(s.notes_count) as notes_end,
                   min(s.leads) as leads_start,
                   max(s.leads) as leads_end
            from accounts a
            left join account_snapshots s
              on s.account_id = a.account_id and s.captured_at >= ? and s.captured_at < ?
            group by a.account_id
            order by a.operator, a.account_name
            """,
            (start, end),
        )
        md = [
            f"# 小红书账号周报 {start_day.isoformat()} 至 {day.isoformat()}",
            "",
            f"- 本周收录笔记：{len(notes)} 条",
            f"- 本周总互动：{sum(r['likes'] + r['collects'] + r['comments'] + r['shares'] for r in notes)}",
            f"- 本周私信/线索：{sum(r['leads'] for r in notes)}",
            "",
            "## 本周爆贴数据",
        ]
        md.extend(_viral_section(notes, "本周"))
        md.extend(
            [
                "",
            "## 账号数据变化",
            "",
            "|账号|运营|赛道|粉丝变化|发帖变化|私信/线索变化|建议|",
            "|---|---|---|---:|---:|---:|---|",
            ]
        )
        for row in accounts:
            followers_delta = _delta(row["followers_start"], row["followers_end"])
            notes_delta = _delta(row["notes_start"], row["notes_end"])
            leads_delta = _delta(row["leads_start"], row["leads_end"])
            advice = _account_advice(followers_delta, notes_delta, leads_delta)
            md.append(
                f"|{row['account_name']}|{row['operator']}|{row['niche'] or '-'}|{followers_delta:+d}|{notes_delta:+d}|{leads_delta:+d}|{advice}|"
            )
        md.extend(["", "## 高优先级笔记"])
        for row in notes[:10]:
            analysis = self.analyzer.analyze_note(_row_to_note(row))
            md.extend(_note_section(row, analysis))
        md.extend(
            [
                "",
                "## 下周运营策略",
                "",
                "1. 优先放大能带来评论咨询和私信的选题，不只按点赞排序。",
                "2. 每个账号至少准备 2 条痛点清单、1 条真实案例、1 条评论区问题复盘。",
                "3. 低互动账号先改标题和封面，再调整发布时间；连续两周低互动再调整赛道切角。",
                "4. 评论区出现明确需求后，当天完成私信承接和需求标签记录。",
                "",
                "## 90 天运营路线图",
                "",
                "- Day 1-30 基础夯实：明确账号人设、统一封面风格、稳定更新频率、建立选题库。",
                "- Day 31-60 流量突破：SEO 关键词优化、复制高互动结构、加强评论区和私信承接、测试内容形式。",
                "- Day 61-90 规模复制：批量产出系列内容、评估商业化时机、数据复盘优化、规划矩阵账号。",
            ]
        )
        return self._write("weekly", day, md, f"小红书周报 {start_day.isoformat()} 至 {day.isoformat()}：收录 {len(notes)} 条笔记。")

    def _write(self, prefix: str, day: date, lines: list[str], summary: str) -> ReportResult:
        md_text = "\n".join(lines) + "\n"
        md_path = self.reports_dir / f"{prefix}-{day.isoformat()}.md"
        html_path = self.reports_dir / f"{prefix}-{day.isoformat()}.html"
        pdf_path = self.reports_dir / f"{prefix}-{day.isoformat()}.pdf"
        md_path.write_text(md_text, encoding="utf-8")
        html_body = markdown.markdown(md_text, extensions=["tables"])
        html_path.write_text(_html_page(html_body), encoding="utf-8")
        _write_pdf(md_text, pdf_path)
        return ReportResult(md_path, html_path, pdf_path, summary)


def _row_to_note(row):
    from .models import NoteMetrics

    published_at = datetime.fromisoformat(row["published_at"]) if row["published_at"] else None
    return NoteMetrics(
        note_id=row["note_id"],
        url=row["url"],
        account_id=row["account_id"],
        title=row["title"],
        body=row["body"],
        published_at=published_at,
        likes=row["likes"],
        collects=row["collects"],
        comments=row["comments"],
        shares=row["shares"],
        views=row["views"],
        leads=row["leads"],
    )


def _dedupe_notes(rows):
    best_by_url = {}
    for row in rows:
        current = best_by_url.get(row["url"])
        if current is None or _note_quality(row) > _note_quality(current):
            best_by_url[row["url"]] = row
    return sorted(best_by_url.values(), key=lambda row: row["captured_at"], reverse=True)


def _note_quality(row) -> tuple[int, int, str]:
    title = row["title"] or ""
    body = row["body"] or ""
    has_title = int(bool(title and title != "待抓取标题"))
    has_body = int(bool(body and "占位数据" not in body and "未配置小红书数据 API" not in body))
    return (has_title, has_body, row["captured_at"])


def _note_section(row, analysis) -> list[str]:
    model_summary = analysis.llm_summary or "规则分析兜底"
    if "402 Payment Required" in model_summary:
        model_summary = "DeepSeek API 余额不足，已使用规则分析兜底。"
    return [
        "",
        f"### {row['title'] or '未命名笔记'}",
        "",
        f"- 链接：{row['url']}",
        f"- 数据：点赞 {row['likes']} / 收藏 {row['collects']} / 评论 {row['comments']} / 分享 {row['shares']} / 私信线索 {row['leads']}",
        f"- 判断：综合 {analysis.total_score}/10，{analysis.content_type}，选题矩阵 {analysis.topic_matrix_score}/100",
        f"- 总结：{model_summary}",
        f"- 主要问题：{_join_limited(analysis.issues, 2)}",
        f"- 执行动作：{_join_limited(analysis.actions, 3)}",
        f"- 下一步：{analysis.next_step}",
    ]


def _daily_strategy_table(notes, analyzer: XhsAnalyzer) -> list[str]:
    if not notes:
        return []
    lines = [
        "",
        "|笔记|数据|问题|修改策略|今日动作|",
        "|---|---|---|---|---|",
    ]
    for row in notes:
        analysis = analyzer.analyze_note(_row_to_note(row))
        title = _table_cell(row["title"] or "未命名笔记", 26)
        data = f"赞{row['likes']} / 藏{row['collects']} / 评{row['comments']}"
        issue = _table_cell(_join_limited(analysis.issues, 1), 42)
        strategy = _table_cell(_join_limited(analysis.actions, 2), 58)
        next_step = _table_cell(analysis.next_step, 34)
        lines.append(f"|{title}|{data}|{issue}|{strategy}|{next_step}|")
    return lines


def _viral_section(notes, label: str) -> list[str]:
    if not notes:
        return [f"{label}暂无可分析笔记。"]
    ranked = sorted(notes, key=_viral_score, reverse=True)
    lines = [
        "",
        "|排名|笔记|爆贴分|点赞|收藏|评论|分享|私信线索|判断|",
        "|---:|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for index, row in enumerate(ranked[:5], start=1):
        title = (row["title"] or "未命名笔记").replace("|", "/")[:28]
        lines.append(
            f"|{index}|{title}|{_viral_score(row)}|{row['likes']}|{row['collects']}|{row['comments']}|{row['shares']}|{row['leads']}|{_viral_judgement(row)}|"
        )
    lines.extend(
        [
            "",
            f"{label}爆贴共性：优先观察收藏、评论、私信线索高的内容。收藏高说明内容有长期价值，评论高说明话题能激发需求，私信线索高说明适合复刻到同系列转化内容。",
        ]
    )
    return lines


def _viral_analysis_section(notes) -> list[str]:
    lines = ["", "## 今日爆贴内容分析", ""]
    if not notes:
        lines.append("今日暂无可分析爆贴内容。")
        return lines
    ranked = sorted(notes, key=_viral_score, reverse=True)[:3]
    for row in ranked:
        title = row["title"] or "未命名笔记"
        reason = _viral_content_reason(row)
        action = _viral_reuse_action(row)
        lines.append(f"- **{title}**：{reason}。复刻方向：{action}")
    return lines


def _monthly_marketing_section(report_date: date) -> list[str]:
    if report_date.month == 6:
        rows = [
            (
                "英国",
                "Dissertation/Proposal 启动，导师沟通弱，道德审批/伦理表/数据处理卡住",
                "毕业论文时间线、Proposal 自救、导师不回消息怎么办、Ethics Form 材料清单",
                "论文全流程辅导 / Proposal 诊断 / 选题与研究问题辅导",
            ),
            (
                "澳洲",
                "S1 出分、挂科焦虑、Appeal/申诉、S2 选课和补救规划",
                "挂科后 48 小时补救流程、Appeal 材料清单、S2 选课避坑",
                "申诉辅导 / 下学期课程包 / 挂科风险评估",
            ),
            (
                "美国",
                "Summer School 节奏快，Quiz/Essay/Exam 密集，补学分压力",
                "暑课时间管理、短学期作业节奏、补学分避坑、考试冲刺计划",
                "暑课辅导 / 包课 / Exam & Quiz 冲刺",
            ),
        ]
    else:
        rows = [
            (
                "英国",
                "围绕当月课程论文、考试、毕业论文或补考节点做痛点内容",
                "按当月 DDL、出分、论文、补考节点拆选题",
                "论文/考试/补考辅导",
            ),
            (
                "澳洲",
                "围绕开学、期中、Final、出分和挂科节点做内容",
                "课程避坑、考试复习、挂科补救、选课规划",
                "课程包 / 申诉辅导 / 考试辅导",
            ),
            (
                "美国",
                "围绕 Midterm、Final、Summer School、Assignment 节点做内容",
                "作业撞车、考试周、暑课补学分、GPA 管理",
                "课程辅导 / 暑课辅导 / GPA 管理",
            ),
        ]
    lines = [
        "",
        "## 当月营销热点",
        "",
        "|地区|本月课业痛点|日报选题方向|可承接产品|",
        "|---|---|---|---|",
    ]
    for region, pain, topic, product in rows:
        lines.append(
            f"|{region}|{_table_cell(pain, 44)}|{_table_cell(topic, 46)}|{_table_cell(product, 30)}|"
        )
    return lines


def _hotspot_section(items: list[dict]) -> list[str]:
    lines = [
        "",
        "## 结合营销开发日历和小红书搜索的留学生爆贴热点内容推荐",
        "",
        "参考《营销开发日历》6月痛点：英国毕业论文/Proposal、澳洲S1出分挂科申诉、美国Summer School。以下仅保留本次搜索中点赞数超过 200 的小红书内容。",
    ]
    if not items:
        lines.append("")
        lines.append("本次未稳定抓取到点赞 200+ 的热点内容，建议稍后重试或检查小红书登录状态。")
        return lines
    lines.extend(
        [
            "",
            "|推荐|搜索词|热点内容|点赞|借鉴方向|",
            "|---:|---|---|---:|---|",
        ]
    )
    for index, item in enumerate(items[:5], start=1):
        raw_title = item.get("title") or "未命名热点"
        title = _markdown_link(_table_cell(raw_title, 34), item.get("url") or "")
        keyword = _table_cell(item.get("keyword") or "-", 18)
        reason = _table_cell(item.get("reason") or "可作为当月选题参考。", 48)
        lines.append(f"|{index}|{keyword}|{title}|{int(item.get('likes') or 0)}|{reason}|")
    return lines


def _viral_content_reason(row) -> str:
    if row["collects"] >= 5:
        return "收藏明显高，说明内容更像清单/攻略/阶段性参考，用户有后续复看的需求"
    if row["comments"] > 0:
        return "评论已有反馈，说明话题能引出真实处境，适合继续追问需求"
    if row["likes"] > 0:
        return "有轻互动基础，但还需要加强可收藏信息密度和评论区承接"
    return "当前互动弱，优先检查标题钩子、封面结果感和正文结构"


def _viral_reuse_action(row) -> str:
    text = (row["title"] or "") + (row["body"] or "")
    if any(word in text for word in ("论文", "dissertation", "proposal", "导师")):
        return "拆成论文时间线、导师沟通话术、开题避坑清单"
    if any(word in text for word in ("挂科", "出分", "appeal", "申诉")):
        return "拆成出分后补救流程、申诉材料清单、风险判断"
    if any(word in text for word in ("复习", "考试", "final")):
        return "拆成考前7天计划、重点抓取方法、挂科风险自测"
    return "保留情绪共鸣标题，正文增加步骤化清单和评论区问题"


def _viral_score(row) -> int:
    return int(row["likes"] + row["collects"] * 2 + row["comments"] * 3 + row["shares"] * 2 + row["leads"] * 8)


def _viral_judgement(row) -> str:
    if row["leads"] > 0:
        return "转化型爆贴，优先复刻"
    if row["comments"] >= 10:
        return "互动型爆贴，跟进评论区"
    if row["collects"] >= row["likes"] and row["collects"] > 0:
        return "收藏型内容，适合做系列"
    if _viral_score(row) > 0:
        return "观察中，补评论承接"
    return "数据不足"


def _join_limited(items: list[str], limit: int) -> str:
    cleaned = [item.strip() for item in items if item.strip()]
    return "；".join(cleaned[:limit]) if cleaned else "暂无"


def _table_cell(text: str, limit: int) -> str:
    cleaned = str(text).replace("|", "/").replace("\n", " ").strip()
    return cleaned[:limit] + ("…" if len(cleaned) > limit else "")


def _markdown_link(text: str, url: str) -> str:
    if not url:
        return text
    return f"[{text}]({url})"


def _delta(start, end) -> int:
    return int(end or 0) - int(start or 0)


def _account_advice(followers_delta: int, notes_delta: int, leads_delta: int) -> str:
    if leads_delta > 0 and followers_delta > 0:
        return "保持当前方向，追加同系列选题"
    if notes_delta <= 0:
        return "先恢复稳定发帖频率"
    if followers_delta <= 0:
        return "强化标题人群和封面结果感"
    return "优化评论区承接，提高私信转化"


def _html_page(body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>小红书运营报告</title>
  <style>
    :root {{
      --ink: #18212f;
      --muted: #6b7280;
      --line: #e8edf3;
      --paper: #ffffff;
      --soft: #f7f9fc;
      --rose: #e94f73;
      --teal: #1f8a84;
      --amber: #f6b44b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at 18% 0%, rgba(233,79,115,.10), transparent 30%),
        radial-gradient(circle at 92% 8%, rgba(31,138,132,.11), transparent 28%),
        #eef3f7;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      line-height: 1.62;
    }}
    main {{
      max-width: 1120px;
      margin: 32px auto;
      padding: 34px 38px 42px;
      background: rgba(255,255,255,.96);
      border: 1px solid rgba(232,237,243,.95);
      border-radius: 18px;
      box-shadow: 0 24px 60px rgba(24,33,47,.10);
    }}
    h1 {{
      margin: -34px -38px 28px;
      padding: 34px 38px 30px;
      color: #fff;
      background: linear-gradient(135deg, #df4668 0%, #1f8a84 100%);
      font-size: 30px;
      line-height: 1.2;
      letter-spacing: 0;
      border-radius: 18px 18px 0 0;
    }}
    h1::after {{
      content: "Red Me Kill · Daily Operations Report";
      display: block;
      margin-top: 10px;
      font-size: 13px;
      font-weight: 500;
      color: rgba(255,255,255,.82);
    }}
    h2 {{
      margin: 34px 0 14px;
      padding-left: 12px;
      border-left: 4px solid var(--rose);
      font-size: 20px;
      line-height: 1.35;
    }}
    h3 {{ margin: 24px 0 10px; font-size: 16px; }}
    p, li {{ color: #354052; }}
    ul:first-of-type {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      padding: 0;
      margin: 0 0 22px;
      list-style: none;
    }}
    ul:first-of-type li {{
      min-height: 78px;
      padding: 16px 18px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: linear-gradient(180deg, #fff, #fbfcfe);
      box-shadow: 0 10px 24px rgba(24,33,47,.05);
      color: var(--muted);
      font-size: 14px;
    }}
    ul:first-of-type li strong, ul:first-of-type li::marker {{ color: var(--rose); }}
    table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      margin: 16px 0 24px;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--paper);
      font-size: 13px;
      box-shadow: 0 10px 26px rgba(24,33,47,.04);
    }}
    th, td {{
      padding: 11px 12px;
      text-align: left;
      vertical-align: top;
      border-bottom: 1px solid var(--line);
      border-right: 1px solid var(--line);
    }}
    th:last-child, td:last-child {{ border-right: 0; }}
    tr:last-child td {{ border-bottom: 0; }}
    th {{
      color: #7c2440;
      background: #fff0f4;
      font-weight: 700;
      white-space: nowrap;
    }}
    tbody tr:nth-child(even) td {{ background: #fbfdff; }}
    tbody tr:hover td {{ background: #f6fbfb; }}
    a {{
      color: #c93659;
      font-weight: 650;
      text-decoration: none;
      border-bottom: 1px solid rgba(201,54,89,.26);
    }}
    a:hover {{ color: #1f8a84; border-bottom-color: rgba(31,138,132,.34); }}
    blockquote {{
      margin: 18px 0;
      padding: 14px 16px;
      border-left: 4px solid var(--teal);
      border-radius: 10px;
      background: #f1faf9;
      color: #335d5a;
    }}
    @media (max-width: 760px) {{
      main {{ margin: 0; padding: 22px 16px 28px; border-radius: 0; }}
      h1 {{ margin: -22px -16px 22px; padding: 26px 18px; border-radius: 0; font-size: 24px; }}
      ul:first-of-type {{ grid-template-columns: 1fr; }}
      table {{ display: block; overflow-x: auto; white-space: nowrap; }}
    }}
    @media print {{
      body {{ background: #fff; }}
      main {{ margin: 0; box-shadow: none; border: 0; border-radius: 0; }}
      h1 {{ border-radius: 0; }}
    }}
  </style>
</head>
<body><main>{body}</main></body>
</html>
"""


def _write_pdf(markdown_text: str, pdf_path: Path) -> None:
    font_name = _register_pdf_font()
    styles = getSampleStyleSheet()
    normal = ParagraphStyle(
        "XhsNormal",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=9.4,
        leading=14,
        spaceAfter=4,
        textColor=colors.HexColor("#29323d"),
    )
    h1 = ParagraphStyle(
        "XhsH1",
        parent=normal,
        fontSize=22,
        leading=29,
        spaceAfter=14,
        textColor=colors.HexColor("#d83f5f"),
    )
    h2 = ParagraphStyle(
        "XhsH2",
        parent=normal,
        fontSize=14.5,
        leading=20,
        spaceBefore=12,
        spaceAfter=6,
        textColor=colors.HexColor("#1f6f78"),
    )
    h3 = ParagraphStyle(
        "XhsH3",
        parent=normal,
        fontSize=12,
        leading=17,
        spaceBefore=6,
        spaceAfter=4,
        textColor=colors.HexColor("#354052"),
    )
    small = ParagraphStyle("XhsSmall", parent=normal, fontSize=7.2, leading=10)
    story = []
    lines = markdown_text.splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 3 * mm))
            index += 1
            continue
        if line.startswith("|"):
            table_lines = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            story.append(_pdf_table(table_lines, small, font_name))
            story.append(Spacer(1, 3 * mm))
            continue
        style = normal
        if line.startswith("# "):
            style = h1
            line = line[2:]
        elif line.startswith("## "):
            style = h2
            line = line[3:]
        elif line.startswith("### "):
            style = h3
            line = line[4:]
        elif line.startswith("- "):
            line = "• " + line[2:]
        story.append(Paragraph(_escape_pdf_text(line), style))
        index += 1
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=22 * mm,
        bottomMargin=18 * mm,
    )
    doc.build(story, onFirstPage=_pdf_page_footer, onLaterPages=_pdf_page_footer)


def _pdf_table(table_lines: list[str], style: ParagraphStyle, font_name: str) -> Table:
    rows = []
    for raw in table_lines:
        cells = [cell.strip() for cell in raw.strip("|").split("|")]
        if cells and all(set(cell) <= {"-", ":"} for cell in cells):
            continue
        rows.append([Paragraph(_escape_pdf_text(cell), style) for cell in cells])
    usable_width = A4[0] - 28 * mm
    col_count = len(rows[0]) if rows else 1
    col_widths = _pdf_col_widths(col_count, usable_width)
    table = Table(rows, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fff0f4")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#8f2944")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fbfdff")]),
                ("GRID", (0, 0), (-1, -1), 0.28, colors.HexColor("#e5ebf2")),
                ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#dce4ee")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4.5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4.5),
                ("TOPPADDING", (0, 0), (-1, -1), 5.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5.5),
            ]
        )
    )
    return table


def _pdf_col_widths(col_count: int, usable_width: float) -> list[float] | None:
    ratios = {
        5: [0.18, 0.14, 0.22, 0.30, 0.16],
        6: [0.09, 0.29, 0.11, 0.10, 0.10, 0.31],
        9: [0.06, 0.25, 0.09, 0.08, 0.08, 0.08, 0.08, 0.10, 0.18],
    }.get(col_count)
    if not ratios:
        return None
    return [usable_width * ratio for ratio in ratios]


def _pdf_page_footer(canvas, doc) -> None:
    width, height = A4
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#17202e"))
    canvas.rect(0, height - 14 * mm, width, 14 * mm, stroke=0, fill=1)
    canvas.setFillColor(colors.HexColor("#ffffff"))
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(14 * mm, height - 8.8 * mm, "Red Me Kill")
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#d9e7e6"))
    canvas.drawRightString(width - 14 * mm, height - 8.8 * mm, "XHS Daily Operations Report")
    canvas.setStrokeColor(colors.HexColor("#eadde4"))
    canvas.setLineWidth(0.6)
    canvas.line(14 * mm, 12 * mm, width - 14 * mm, 12 * mm)
    canvas.setFillColor(colors.HexColor("#b9aab3"))
    canvas.setFont("Helvetica", 7)
    canvas.drawString(14 * mm, 8 * mm, "XHS Agent · Internal Operations Report")
    canvas.drawRightString(width - 14 * mm, 8 * mm, f"Page {doc.page}")
    canvas.setFillColor(colors.HexColor("#f6e9ee"))
    canvas.setFont("Helvetica", 22)
    canvas.drawCentredString(width / 2, 8 * mm, "Domi XHS Agent")
    canvas.restoreState()


def _register_pdf_font() -> str:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
    ]
    for path in candidates:
        font_path = Path(path)
        if font_path.exists():
            try:
                pdfmetrics.registerFont(TTFont("XhsCJK", str(font_path)))
                return "XhsCJK"
            except Exception:
                continue
    return "Helvetica"


def _escape_pdf_text(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
