from __future__ import annotations

import uuid

from scraper.adapter import TrendRecord


def update_trend_state(
    trend: TrendRecord,
    in_top_this_week: bool,
    current_engagement: int,
    config: dict,
) -> TrendRecord:
    emerging_weeks = config.get("emerging_to_active_weeks", 2)
    velocity_promote = config.get("velocity_promote_pct", 50)
    rank_drop_threshold = config.get("rank_drop_threshold", 10)
    grace_period = config.get("grace_period_weeks", 3)
    engagement_floor = config.get("engagement_floor", 50000)

    prev_engagement = trend.engagement_history[-1] if trend.engagement_history else 0
    engagement_fell_60 = (
        prev_engagement > 0
        and current_engagement < prev_engagement * 0.4
    )

    if trend.state == "EMERGING":
        if (
            trend.weeks_active >= emerging_weeks
            or trend.velocity_pct > velocity_promote
        ):
            trend = trend.model_copy(update={"state": "ACTIVE"})

    elif trend.state == "ACTIVE":
        rank_dropped = (
            len(trend.rank_history) >= 2
            and (trend.rank_history[-1] - trend.rank_history[-2]) > rank_drop_threshold
        )
        if not in_top_this_week or rank_dropped or engagement_fell_60:
            trend = trend.model_copy(update={"state": "DECLINING"})

    elif trend.state == "DECLINING":
        if (
            trend.weeks_missing >= grace_period
            and current_engagement < engagement_floor
        ):
            trend = trend.model_copy(update={"state": "ARCHIVED"})

    elif trend.state == "ARCHIVED":
        if in_top_this_week:
            trend = trend.model_copy(update={"state": "ACTIVE", "weeks_missing": 0})

    return trend


def create_new_trend(cluster: dict, category: str, rank: int, week: str) -> TrendRecord:
    primary_hashtag = cluster.get("primary_hashtag", "")
    related_hashtags = cluster.get("related_hashtags", [])
    topic_label = cluster.get("topic_label", primary_hashtag.lstrip("#"))
    videos = cluster.get("videos", [])

    total_engagement = sum(
        (v.views + v.likes + v.comments + v.shares) for v in videos
    )

    top_creators: list[dict] = []
    seen_creators: set[str] = set()
    for v in sorted(videos, key=lambda x: x.views, reverse=True):
        if v.author_username not in seen_creators:
            top_creators.append({
                "username": v.author_username,
                "display_name": v.author_display_name,
                "followers": v.author_followers,
            })
            seen_creators.add(v.author_username)
        if len(top_creators) >= 5:
            break

    sound_counter: dict[str, dict] = {}
    for v in videos:
        if v.sound_id:
            if v.sound_id not in sound_counter:
                sound_counter[v.sound_id] = {
                    "sound_id": v.sound_id,
                    "title": v.sound_title,
                    "author": v.sound_author,
                    "count": 0,
                }
            sound_counter[v.sound_id]["count"] += 1

    top_sounds = sorted(sound_counter.values(), key=lambda x: x["count"], reverse=True)[:3]
    sample_videos = [v.video_id for v in videos[:5]]

    trend_id = f"{category}_{primary_hashtag.lstrip('#')}_{week}".replace(" ", "_")

    return TrendRecord(
        trend_id=trend_id,
        label=topic_label,
        category=category,
        primary_hashtag=primary_hashtag,
        related_hashtags=related_hashtags,
        topic_label=topic_label,
        state="EMERGING",
        first_seen=week,
        last_seen=week,
        weeks_active=1,
        weeks_missing=0,
        current_rank=rank,
        rank_history=[rank],
        engagement_history=[total_engagement],
        velocity_pct=0.0,
        momentum_score=0.0,
        predicted_peak=None,
        crossover_categories=[],
        top_creators=top_creators,
        top_sounds=top_sounds,
        sample_videos=sample_videos,
    )
