from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class VideoMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    video_id: str
    url: str
    author_username: str
    author_display_name: str
    author_followers: int
    caption: str
    hashtags: list[str]
    mentions: list[str]
    sound_id: str
    sound_title: str
    sound_author: str
    views: int
    likes: int
    comments: int
    shares: int
    duration_sec: int
    posted_at: datetime
    scraped_at: datetime
    thumbnail_url: str


class TrendRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    trend_id: str
    label: str
    category: str
    primary_hashtag: str
    related_hashtags: list[str]
    topic_label: str
    state: str  # EMERGING | ACTIVE | DECLINING | ARCHIVED
    first_seen: str  # YYYY-WW
    last_seen: str
    weeks_active: int
    weeks_missing: int
    current_rank: int
    rank_history: list[int]
    engagement_history: list[int]
    velocity_pct: float
    momentum_score: float
    predicted_peak: str | None
    crossover_categories: list[str]
    top_creators: list[dict]
    top_sounds: list[dict]
    sample_videos: list[str]


class WeeklyReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    week: str
    new: list[str]
    promoted: list[str]
    declining: list[str]
    archived: list[str]
    reactivated: list[str]
    still_active: list[str]
    crossovers: list[str]
    rising_fast: list[str]
    near_peak: list[str]
