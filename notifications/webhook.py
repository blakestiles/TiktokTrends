from __future__ import annotations

import httpx
from loguru import logger

from scraper.adapter import WeeklyReport


def send_discord(webhook_url: str, content: str) -> None:
    if not webhook_url:
        logger.debug("Discord webhook URL not configured, skipping")
        return
    try:
        resp = httpx.post(webhook_url, json={"content": content}, timeout=10)
        resp.raise_for_status()
        logger.info("Discord notification sent")
    except Exception as e:
        logger.error(f"Failed to send Discord notification: {e}")


def send_slack(webhook_url: str, text: str) -> None:
    if not webhook_url:
        logger.debug("Slack webhook URL not configured, skipping")
        return
    try:
        resp = httpx.post(webhook_url, json={"text": text}, timeout=10)
        resp.raise_for_status()
        logger.info("Slack notification sent")
    except Exception as e:
        logger.error(f"Failed to send Slack notification: {e}")


def notify_weekly_report(config: dict, report: WeeklyReport) -> None:
    lines = [
        f"**TikTok Trend Tracker — Week {report.week}**",
        f"New trends: {len(report.new)}",
        f"Promoted to Active: {len(report.promoted)}",
        f"Declining: {len(report.declining)}",
        f"Archived: {len(report.archived)}",
        f"Reactivated: {len(report.reactivated)}",
        f"Still Active: {len(report.still_active)}",
        f"Crossovers: {len(report.crossovers)}",
        f"Rising Fast: {len(report.rising_fast)}",
        f"Near Peak: {len(report.near_peak)}",
    ]

    if report.new:
        lines.append(f"New IDs: {', '.join(report.new[:5])}")
    if report.archived:
        lines.append(f"Archived IDs: {', '.join(report.archived[:5])}")

    message = "\n".join(lines)

    notifications = config.get("notifications", {})
    discord_url = notifications.get("discord_webhook", "") or ""
    slack_url = notifications.get("slack_webhook", "") or ""

    send_discord(discord_url, message)
    send_slack(slack_url, message)
