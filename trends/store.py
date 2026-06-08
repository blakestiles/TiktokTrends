from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml
from loguru import logger

from scraper.adapter import TrendRecord, WeeklyReport
from scraper.classifier import CATEGORY_CONFIG, classify_video, get_primary_category
from scraper.fetcher import fetch_by_hashtag, fetch_trending
from grouping.hashtag_buckets import bucket_by_hashtag
from grouping.topic_cluster import cluster_topics
from trends.crossover import detect_crossovers
from trends.db import (
    get_active_trends,
    init_db,
    save_weekly_snapshot,
    upsert_trend,
)
from trends.lifecycle import create_new_trend, update_trend_state
from trends.momentum import compute_momentum, predict_peak

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "trends.duckdb"
ACTIVE_DIR = ROOT / "data" / "active"
RUNS_DIR = ROOT / "runs"
OVERRIDES_PATH = ROOT / "overrides.yaml"


def get_current_week() -> str:
    now = datetime.now(timezone.utc)
    iso = now.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _load_overrides() -> dict:
    if OVERRIDES_PATH.exists():
        with open(OVERRIDES_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def run_weekly(config: dict) -> WeeklyReport:
    week = get_current_week()
    logger.info(f"Starting weekly run for week {week}")

    overrides = _load_overrides()
    exclude_hashtags = overrides.get("exclude_hashtags", [])
    pinned = set(overrides.get("pin", []))

    ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    conn = init_db(DB_PATH)

    categories = config.get("categories", ["games", "card_games", "games_marketing"])
    top_n = config.get("top_n_per_week", 20)
    min_score = config.get("classifier_min_score", 0.6)
    sim_threshold = config.get("topic_cluster_similarity", 0.75)
    weights = config.get("momentum_weights", {"velocity": 0.5, "rank": 0.3, "engagement": 0.2})

    report_new: list[str] = []
    report_promoted: list[str] = []
    report_declining: list[str] = []
    report_archived: list[str] = []
    report_reactivated: list[str] = []
    report_still_active: list[str] = []
    report_crossovers: list[str] = []
    report_rising_fast: list[str] = []
    report_near_peak: list[str] = []

    all_updated_trends: dict[str, list[TrendRecord]] = {}

    for category in categories:
        logger.info(f"Processing category: {category}")

        videos = fetch_trending(config, count=50)

        cat_cfg = CATEGORY_CONFIG.get(category, {})
        for hashtag in cat_cfg.get("hashtags", [])[:3]:
            extra = fetch_by_hashtag(hashtag, config, count=30)
            videos.extend(extra)

        cat_videos = []
        for v in videos:
            scores = classify_video(v, CATEGORY_CONFIG)
            primary = get_primary_category(scores, min_score)
            if primary == category:
                cat_videos.append(v)

        logger.info(f"Category {category}: {len(cat_videos)} classified videos")

        buckets = bucket_by_hashtag(cat_videos, exclude=exclude_hashtags)
        clusters = cluster_topics(buckets, similarity_threshold=sim_threshold)
        clusters = clusters[:top_n]

        existing_trends = get_active_trends(conn, category)
        existing_by_id = {t.trend_id: t for t in existing_trends}

        cluster_hashtags = {c["primary_hashtag"] for c in clusters}

        seen_trend_ids: set[str] = set()
        updated_trends: list[TrendRecord] = []

        for rank, cluster in enumerate(clusters, start=1):
            primary_tag = cluster["primary_hashtag"]
            cluster_videos = cluster.get("videos", [])
            current_engagement = sum(
                v.views + v.likes + v.comments + v.shares for v in cluster_videos
            )

            existing_match: TrendRecord | None = None
            for t in existing_trends:
                if t.primary_hashtag == primary_tag:
                    existing_match = t
                    break

            if existing_match:
                prev_state = existing_match.state
                prev_eng = existing_match.engagement_history[-1] if existing_match.engagement_history else 0
                velocity = ((current_engagement - prev_eng) / prev_eng * 100) if prev_eng > 0 else 0.0

                updated = existing_match.model_copy(update={
                    "last_seen": week,
                    "weeks_active": existing_match.weeks_active + 1,
                    "current_rank": rank,
                    "rank_history": existing_match.rank_history + [rank],
                    "engagement_history": existing_match.engagement_history + [current_engagement],
                    "velocity_pct": velocity,
                })
                updated = update_trend_state(updated, in_top_this_week=True, current_engagement=current_engagement, config=config)
                updated = updated.model_copy(update={
                    "momentum_score": compute_momentum(updated, weights),
                    "predicted_peak": predict_peak(updated),
                })

                if prev_state == "ARCHIVED" and updated.state == "ACTIVE":
                    report_reactivated.append(updated.trend_id)
                elif prev_state == "EMERGING" and updated.state == "ACTIVE":
                    report_promoted.append(updated.trend_id)
                elif updated.state == "DECLINING" and prev_state == "ACTIVE":
                    report_declining.append(updated.trend_id)
                elif updated.state == "ARCHIVED" and prev_state != "ARCHIVED":
                    report_archived.append(updated.trend_id)
                elif updated.state in ("ACTIVE", "EMERGING"):
                    report_still_active.append(updated.trend_id)

                seen_trend_ids.add(updated.trend_id)
                updated_trends.append(updated)
            else:
                new_trend = create_new_trend(cluster, category, rank, week)
                if new_trend.trend_id in pinned:
                    new_trend = new_trend.model_copy(update={"state": "ACTIVE"})
                report_new.append(new_trend.trend_id)
                seen_trend_ids.add(new_trend.trend_id)
                updated_trends.append(new_trend)

        for trend_id, trend in existing_by_id.items():
            if trend_id not in seen_trend_ids:
                prev_state = trend.state
                updated = trend.model_copy(update={
                    "weeks_missing": trend.weeks_missing + 1,
                })
                prev_eng = updated.engagement_history[-1] if updated.engagement_history else 0
                updated = update_trend_state(updated, in_top_this_week=False, current_engagement=prev_eng, config=config)
                if updated.state == "DECLINING" and prev_state == "ACTIVE":
                    report_declining.append(updated.trend_id)
                elif updated.state == "ARCHIVED" and prev_state != "ARCHIVED":
                    report_archived.append(updated.trend_id)
                updated_trends.append(updated)

        for trend in updated_trends:
            if trend.velocity_pct > config.get("velocity_promote_pct", 50):
                if trend.trend_id not in report_rising_fast:
                    report_rising_fast.append(trend.trend_id)
            if trend.predicted_peak == week:
                if trend.trend_id not in report_near_peak:
                    report_near_peak.append(trend.trend_id)

        for trend in updated_trends:
            upsert_trend(conn, trend)

        save_weekly_snapshot(conn, week, updated_trends)

        active_export = [t.model_dump(mode="json") for t in updated_trends if t.state != "ARCHIVED"]
        out_path = ACTIVE_DIR / f"{category}.json"
        out_path.write_text(json.dumps(active_export, indent=2, default=str), encoding="utf-8")
        logger.info(f"Wrote {len(active_export)} active trends to {out_path}")

        all_updated_trends[category] = updated_trends

    crossover_trends = detect_crossovers(all_updated_trends)
    for ct in crossover_trends:
        if ct.crossover_categories and ct.trend_id not in report_crossovers:
            report_crossovers.append(ct.trend_id)
            upsert_trend(conn, ct)

    report = WeeklyReport(
        week=week,
        new=report_new,
        promoted=report_promoted,
        declining=report_declining,
        archived=report_archived,
        reactivated=report_reactivated,
        still_active=report_still_active,
        crossovers=report_crossovers,
        rising_fast=report_rising_fast,
        near_peak=report_near_peak,
    )

    report_path = RUNS_DIR / f"{week}-report.json"
    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    logger.info(f"Saved weekly report to {report_path}")

    conn.close()
    return report
