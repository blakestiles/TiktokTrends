from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

_scheduler: BackgroundScheduler | None = None


def _run_weekly_job(config: dict) -> None:
    from trends.store import run_weekly
    from notifications.webhook import notify_weekly_report

    logger.info("Scheduled weekly job starting")
    try:
        report = run_weekly(config)
        notify_weekly_report(config, report)
        logger.info(f"Scheduled weekly job completed for week {report.week}")
    except Exception as e:
        logger.error(f"Scheduled weekly job failed: {e}")


def start_scheduler(config: dict) -> None:
    global _scheduler

    _scheduler = BackgroundScheduler()
    trigger = CronTrigger(day_of_week="mon", hour=9, minute=0)
    _scheduler.add_job(
        _run_weekly_job,
        trigger=trigger,
        args=[config],
        id="weekly_trend_job",
        name="Weekly TikTok Trend Scrape",
        replace_existing=True,
    )
    _scheduler.start()

    jobs = _scheduler.get_jobs()
    for job in jobs:
        next_run = job.next_run_time
        logger.info(f"Scheduler started. Job '{job.name}' next run: {next_run}")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
        _scheduler = None
