from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv
from loguru import logger

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

CONFIG_PATH = ROOT / "config.yaml"
RUNS_DIR = ROOT / "runs"
DEBUG_DIR = ROOT / "data" / "debug"


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def cmd_scrape(args: argparse.Namespace, config: dict) -> None:
    from trends.store import run_weekly
    from notifications.webhook import notify_weekly_report

    logger.info("Running manual scrape")
    report = run_weekly(config)
    notify_weekly_report(config, report)
    logger.info(f"Scrape complete. Week: {report.week}")
    print(json.dumps(report.model_dump(), indent=2, default=str))


def cmd_serve(args: argparse.Namespace, config: dict) -> None:
    import uvicorn

    port = config.get("viewer_port", 3000)
    logger.info(f"Starting viewer on port {port}")
    uvicorn.run("viewer.server:app", host="0.0.0.0", port=port, reload=False)


def cmd_schedule(args: argparse.Namespace, config: dict) -> None:
    import time

    from scheduler.weekly_job import start_scheduler, stop_scheduler

    logger.info("Starting APScheduler (press Ctrl+C to stop)")
    start_scheduler(config)
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Interrupt received, shutting down scheduler")
        stop_scheduler()


def cmd_report(args: argparse.Namespace, config: dict) -> None:
    week = args.week
    if not week:
        report_files = sorted(RUNS_DIR.glob("*-report.json"))
        if not report_files:
            print("No reports found in runs/")
            sys.exit(1)
        report_path = report_files[-1]
    else:
        report_path = RUNS_DIR / f"{week}-report.json"

    if not report_path.exists():
        print(f"Report not found: {report_path}")
        sys.exit(1)

    data = json.loads(report_path.read_text(encoding="utf-8"))
    print(json.dumps(data, indent=2))

    print("\n--- Summary ---")
    print(f"Week:          {data.get('week', '?')}")
    print(f"New trends:    {len(data.get('new', []))}")
    print(f"Promoted:      {len(data.get('promoted', []))}")
    print(f"Declining:     {len(data.get('declining', []))}")
    print(f"Archived:      {len(data.get('archived', []))}")
    print(f"Reactivated:   {len(data.get('reactivated', []))}")
    print(f"Still Active:  {len(data.get('still_active', []))}")
    print(f"Crossovers:    {len(data.get('crossovers', []))}")
    print(f"Rising Fast:   {len(data.get('rising_fast', []))}")
    print(f"Near Peak:     {len(data.get('near_peak', []))}")


def cmd_replay(args: argparse.Namespace, config: dict) -> None:
    from trends.db import get_weekly_snapshot, init_db
    from trends.lifecycle import update_trend_state
    from trends.momentum import compute_momentum, predict_peak

    week_from = args.fr
    week_to = args.to
    category = args.category

    conn = init_db(ROOT / "data" / "trends.duckdb")
    weights = config.get("momentum_weights", {"velocity": 0.5, "rank": 0.3, "engagement": 0.2})

    snapshots_in_range: list[tuple[str, list]] = []
    runs_files = sorted(RUNS_DIR.glob("*-report.json"))
    for rf in runs_files:
        week = rf.stem.replace("-report", "")
        if week_from <= week <= week_to:
            trends = get_weekly_snapshot(conn, week, category)
            if trends:
                snapshots_in_range.append((week, trends))

    conn.close()

    if not snapshots_in_range:
        print(f"No snapshots found for category={category} between {week_from} and {week_to}")
        sys.exit(0)

    print(f"Replaying {len(snapshots_in_range)} weeks for category={category}")

    for week, trends in snapshots_in_range:
        print(f"\n=== Week {week} ===")
        for trend in trends:
            eng = trend.engagement_history[-1] if trend.engagement_history else 0
            updated = update_trend_state(trend, in_top_this_week=True, current_engagement=eng, config=config)
            momentum = compute_momentum(updated, weights)
            peak = predict_peak(updated)
            print(
                f"  {trend.trend_id:50s} state={updated.state:10s} "
                f"momentum={momentum:.3f} peak={peak}"
            )


def cmd_debug(args: argparse.Namespace, config: dict) -> None:
    week = args.week

    if not week:
        debug_files = sorted(DEBUG_DIR.glob("*-playwright-raw.json"))
        if not debug_files:
            print("No debug files found in data/debug/")
            sys.exit(0)
        for f in debug_files[-5:]:
            print(f.name)
        return

    matches = list(DEBUG_DIR.glob(f"*{week}*"))
    if not matches:
        print(f"No debug files matching week/date '{week}' in data/debug/")
        sys.exit(0)

    for match in matches:
        print(f"\n=== {match.name} ===")
        try:
            data = json.loads(match.read_text(encoding="utf-8"))
            count = data.get("intercepted_count", 0)
            print(f"Intercepted items: {count}")
            items = data.get("items", [])
            for i, item in enumerate(items[:3]):
                print(f"  [{i}] id={item.get('id','?')} desc={str(item.get('desc',''))[:60]}")
            if len(items) > 3:
                print(f"  ... and {len(items)-3} more")
        except Exception as e:
            print(f"  Could not parse: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="trend-tracker",
        description="TikTok Trend Tracker CLI",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("scrape", help="Run weekly scrape immediately")

    subparsers.add_parser("serve", help="Start the FastAPI viewer")

    subparsers.add_parser("schedule", help="Start APScheduler (blocks)")

    report_p = subparsers.add_parser("report", help="Print a weekly report")
    report_p.add_argument("--week", default=None, help="YYYY-WW (defaults to latest)")

    replay_p = subparsers.add_parser("replay", help="Replay lifecycle on historical snapshots")
    replay_p.add_argument("--from", dest="fr", required=True, help="Start week YYYY-WW")
    replay_p.add_argument("--to", required=True, help="End week YYYY-WW")
    replay_p.add_argument("--category", required=True, help="Category name")

    debug_p = subparsers.add_parser("debug", help="Print raw playwright debug payloads")
    debug_p.add_argument("--week", default=None, help="Date string to filter files")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    config = load_config()

    dispatch = {
        "scrape": cmd_scrape,
        "serve": cmd_serve,
        "schedule": cmd_schedule,
        "report": cmd_report,
        "replay": cmd_replay,
        "debug": cmd_debug,
    }
    dispatch[args.command](args, config)


if __name__ == "__main__":
    main()
