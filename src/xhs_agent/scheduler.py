from __future__ import annotations

from datetime import datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import Settings


def run_scheduler(settings: Settings) -> None:
    from .cli import _build_report, _sync_all
    from .messaging import deliver_report
    from .repository import Repository
    from .xhs_browser import collect_notes_with_chrome
    from .xhs_hotspots import collect_daily_hotspots

    repo = Repository(settings.agent.database_path)
    repo.migrate()
    scheduler = BlockingScheduler(timezone=settings.agent.timezone)

    daily_hour, daily_minute = _parse_time(settings.schedule.daily_report_time)
    weekly_hour, weekly_minute = _parse_time(settings.schedule.weekly_report_time)

    def daily_job() -> None:
        report_day = datetime.now().date() - timedelta(days=1)
        _sync_all(repo, settings)
        collect_notes_with_chrome(repo, report_date=report_day)
        collect_daily_hotspots(report_day)
        result = _build_report(repo, settings, "daily", report_day.isoformat())
        deliver_report(settings, result)

    def weekly_job() -> None:
        _sync_all(repo, settings)
        result = _build_report(repo, settings, "weekly")
        deliver_report(settings, result)

    scheduler.add_job(daily_job, CronTrigger(hour=daily_hour, minute=daily_minute), name="小红书日报")
    scheduler.add_job(
        weekly_job,
        CronTrigger(day_of_week=settings.schedule.weekly_report_day, hour=weekly_hour, minute=weekly_minute),
        name="小红书周报",
    )
    print("定时器已启动：日报和周报会按配置自动运行。")
    scheduler.start()


def _parse_time(value: str) -> tuple[int, int]:
    hour, minute = value.split(":", 1)
    return int(hour), int(minute)
