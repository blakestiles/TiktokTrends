from __future__ import annotations

import os
import random
import re
import time
from datetime import datetime, timezone

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from scraper.adapter import VideoMetadata

RAPIDAPI_HOST = "tiktok-scraper7.p.rapidapi.com"
BASE_URL = f"https://{RAPIDAPI_HOST}"

_challenge_id_cache: dict[str, str] = {}


def _get_headers() -> dict:
    api_key = os.environ.get("OMKARCLOUD_API_KEY", "")
    return {
        "x-rapidapi-host": RAPIDAPI_HOST,
        "x-rapidapi-key": api_key,
    }


def _sleep(config: dict) -> None:
    delay = config.get("scrape", {}).get("request_delay_sec", 4)
    jitter = config.get("scrape", {}).get("jitter_sec", 2)
    sleep_time = delay + random.uniform(0, jitter)
    logger.debug(f"Sleeping {sleep_time:.1f}s between requests")
    time.sleep(sleep_time)


def _extract_hashtags_from_title(title: str) -> list[str]:
    return [f"#{m}" for m in re.findall(r"#(\w+)", title)]


def _raw_to_video_metadata(raw: dict) -> VideoMetadata:
    now = datetime.now(timezone.utc)

    title = raw.get("title", "") or ""
    content_desc = raw.get("content_desc", []) or []

    hashtags: list[str] = []
    if content_desc:
        for item in content_desc:
            text = item.strip() if isinstance(item, str) else str(item).strip()
            if text.startswith("#"):
                hashtags.append(text.rstrip())
    if not hashtags:
        hashtags = _extract_hashtags_from_title(title)

    mentions: list[str] = []
    for word in title.split():
        if word.startswith("@"):
            mentions.append(word)

    author = raw.get("author", {}) or {}
    music_info = raw.get("music_info", {}) or {}

    create_time = raw.get("create_time", 0) or 0
    try:
        posted_at = datetime.fromtimestamp(int(create_time), tz=timezone.utc)
    except (ValueError, OSError):
        posted_at = now

    return VideoMetadata(
        video_id=str(raw.get("video_id", raw.get("aweme_id", ""))),
        url=raw.get("play", "") or "",
        author_username=str(author.get("unique_id", "")),
        author_display_name=str(author.get("nickname", "")),
        author_followers=int(author.get("follower_count", 0) or 0),
        caption=title,
        hashtags=hashtags,
        mentions=mentions,
        sound_id=str(music_info.get("id", "")),
        sound_title=str(music_info.get("title", "")),
        sound_author=str(music_info.get("author", "")),
        views=int(raw.get("play_count", 0) or 0),
        likes=int(raw.get("digg_count", 0) or 0),
        comments=int(raw.get("comment_count", 0) or 0),
        shares=int(raw.get("share_count", 0) or 0),
        duration_sec=int(raw.get("duration", 0) or 0),
        posted_at=posted_at,
        scraped_at=now,
        thumbnail_url=raw.get("cover", "") or "",
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _get(url: str, params: dict | None = None) -> dict:
    with httpx.Client(timeout=30) as client:
        resp = client.get(url, headers=_get_headers(), params=params)
        resp.raise_for_status()
        return resp.json()


def _get_challenge_id(hashtag: str) -> str | None:
    tag = hashtag.lstrip("#")
    if tag in _challenge_id_cache:
        return _challenge_id_cache[tag]
    try:
        data = _get(f"{BASE_URL}/challenge/search", params={"keywords": tag, "count": 1})
        challenge_list = data.get("data", {}).get("challenge_list", [])
        if challenge_list:
            cid = str(challenge_list[0]["id"])
            _challenge_id_cache[tag] = cid
            logger.debug(f"Resolved #{tag} → challenge_id={cid}")
            return cid
    except Exception as e:
        logger.warning(f"Could not resolve challenge_id for #{tag}: {e}")
    return None


def fetch_trending(config: dict, count: int = 50) -> list[VideoMetadata]:
    logger.info(f"Fetching {count} trending videos from omkarcloud (region=US)")
    try:
        data = _get(f"{BASE_URL}/feed/list", params={"count": count, "region": "US"})
        items = data.get("data", []) or []
        if not items and isinstance(data, list):
            items = data
        _sleep(config)
        videos = []
        for raw in items:
            try:
                videos.append(_raw_to_video_metadata(raw))
            except Exception as e:
                logger.warning(f"Skipping malformed video record: {e}")
        logger.info(f"Fetched {len(videos)} trending videos")
        return videos
    except Exception as e:
        logger.error(f"fetch_trending failed after retries: {e}, falling back to playwright")
        return _playwright_fallback(config)


def fetch_by_hashtag(hashtag: str, config: dict, count: int = 30) -> list[VideoMetadata]:
    tag = hashtag.lstrip("#")
    logger.info(f"Fetching videos for hashtag #{tag}")

    challenge_id = _get_challenge_id(tag)
    if not challenge_id:
        logger.warning(f"No challenge_id found for #{tag}, skipping")
        return []

    try:
        data = _get(f"{BASE_URL}/challenge/posts", params={"challenge_id": challenge_id, "count": count})
        items = data.get("data", {}).get("videos", []) or data.get("data", []) or []
        if not items and isinstance(data.get("data"), list):
            items = data["data"]
        _sleep(config)
        videos = []
        for raw in items:
            try:
                videos.append(_raw_to_video_metadata(raw))
            except Exception as e:
                logger.warning(f"Skipping malformed video record: {e}")
        logger.info(f"Fetched {len(videos)} videos for #{tag}")
        return videos
    except Exception as e:
        logger.error(f"fetch_by_hashtag #{tag} failed: {e}")
        return []


def _playwright_fallback(config: dict) -> list[VideoMetadata]:
    import asyncio
    from scraper.providers.playwright_provider import fetch_trending_playwright

    logger.info("Using playwright fallback scraper")
    try:
        raw_items = asyncio.run(fetch_trending_playwright())
        videos = []
        for raw in raw_items:
            try:
                videos.append(_raw_to_video_metadata(raw))
            except Exception as e:
                logger.warning(f"Skipping playwright video record: {e}")
        logger.info(f"Playwright fallback returned {len(videos)} videos")
        return videos
    except Exception as e:
        logger.error(f"Playwright fallback also failed: {e}")
        return []
