from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

from .analysis import XhsAnalyzer
from .config import load_accounts, load_manual_links, load_settings, load_wechat_transcript_links
from .llm import DeepSeekClient
from .messaging import deliver_report
from .repository import Repository
from .reports import ReportBuilder
from .scheduler import run_scheduler
from .wechat_capture import import_clipboard_to_manual_links, watch_clipboard
from .xhs_hotspots import collect_daily_hotspots
from .xhs_browser import collect_notes_with_chrome, open_xhs_login_page
from .xhs_api import XhsApiClient


def main() -> None:
    parser = argparse.ArgumentParser(description="小红书账号运营分析 Agent")
    parser.add_argument(
        "command",
        choices=[
            "sync",
            "daily",
            "weekly",
            "run",
            "init-db",
            "wechat-import-clipboard",
            "wechat-watch-clipboard",
            "xhs-browser-login",
            "xhs-browser-collect",
        ],
    )
    parser.add_argument("--config", default="config/settings.toml")
    parser.add_argument("--dry-run", action="store_true", help="只生成报告，不发送飞书")
    parser.add_argument("--send", action="store_true", help="审核通过后才发送企业微信/微信")
    parser.add_argument("--sender", default="wechat", help="微信导入来源标记")
    parser.add_argument("--interval", type=float, default=2.0, help="剪贴板监听间隔秒数")
    parser.add_argument("--limit", type=int, default=None, help="浏览器采集链接数量上限")
    parser.add_argument("--wait", type=float, default=5.0, help="每个小红书页面等待加载秒数")
    parser.add_argument("--date", default=None, help="报告日期，格式 YYYY-MM-DD")
    parser.add_argument("--yesterday", action="store_true", help="生成昨天日期的日报/周报")
    parser.add_argument("--refresh-all", action="store_true", help="浏览器采集时刷新所有链接，默认只采未抓取链接")
    args = parser.parse_args()

    settings = load_settings(args.config)
    repo = Repository(settings.agent.database_path)
    repo.migrate()

    if args.command == "init-db":
        _sync_accounts(repo, settings)
        print("数据库初始化完成")
        return

    if args.command == "sync":
        _sync_all(repo, settings)
        return

    if args.command == "wechat-import-clipboard":
        added = import_clipboard_to_manual_links(settings.agent.manual_links_csv, args.sender)
        print(f"导入完成：新增 {added} 条小红书链接")
        return

    if args.command == "wechat-watch-clipboard":
        watch_clipboard(settings.agent.manual_links_csv, args.sender, args.interval)
        return

    if args.command == "xhs-browser-login":
        open_xhs_login_page()
        return

    if args.command == "xhs-browser-collect":
        collected = collect_notes_with_chrome(repo, args.wait, args.limit, args.refresh_all)
        print(f"浏览器采集完成：写入 {collected} 条笔记数据")
        return

    if args.command in {"daily", "weekly"}:
        report_day = _report_day(args)
        _sync_all(repo, settings)
        if args.command == "daily":
            collected = collect_notes_with_chrome(repo, args.wait, args.limit, args.refresh_all, report_day)
            print(f"浏览器采集完成：写入 {collected} 条笔记数据")
            collect_daily_hotspots(report_day)
        result = _build_report(repo, settings, args.command, report_day.isoformat())
        deliver_report(settings, result, args.dry_run or not args.send)
        print(result.markdown_path.resolve())
        print(result.html_path.resolve())
        print(result.pdf_path.resolve())
        return

    if args.command == "run":
        run_scheduler(settings)


def _report_day(args) -> date:
    if args.date and args.yesterday:
        raise ValueError("--date 和 --yesterday 只能选一个")
    if args.date:
        return date.fromisoformat(args.date)
    if args.yesterday:
        return datetime.now().date() - timedelta(days=1)
    return datetime.now().date()


def _sync_all(repo: Repository, settings) -> None:
    _sync_accounts(repo, settings)
    links = []
    if settings.wechat_input.enabled:
        links.extend(load_wechat_transcript_links(settings.wechat_input.transcript_path))
    links.extend(load_manual_links(settings.agent.manual_links_csv))
    added = repo.add_links(links)

    xhs = XhsApiClient(settings.xhs_api)
    note_urls = repo.known_note_urls()
    notes = [xhs.fetch_note(url) for url in note_urls]
    repo.upsert_note_metrics(notes)

    accounts = load_accounts(settings.agent.accounts_csv)
    snapshots = [xhs.fetch_account_snapshot(account) for account in accounts]
    repo.add_account_snapshots(snapshots)
    print(f"同步完成：新增链接 {added} 条，抓取笔记 {len(notes)} 条，账号快照 {len(snapshots)} 条")


def _sync_accounts(repo: Repository, settings) -> None:
    accounts = load_accounts(settings.agent.accounts_csv)
    repo.upsert_accounts(accounts)


def _build_report(repo: Repository, settings, kind: str, report_date: str | None = None):
    knowledge_path = Path(settings.agent.knowledge_file)
    knowledge = knowledge_path.read_text(encoding="utf-8") if knowledge_path.exists() else ""
    llm_client = DeepSeekClient(settings.llm, knowledge)
    builder = ReportBuilder(repo, XhsAnalyzer(knowledge, llm_client), settings.agent.reports_dir)
    day = date.fromisoformat(report_date) if report_date else datetime.now().date()
    if kind == "daily":
        return builder.build_daily(day)
    return builder.build_weekly(day)


if __name__ == "__main__":
    main()
