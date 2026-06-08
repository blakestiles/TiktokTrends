from __future__ import annotations

from scraper.adapter import VideoMetadata


def bucket_by_hashtag(
    videos: list[VideoMetadata],
    exclude: list[str],
) -> dict[str, list[VideoMetadata]]:
    exclude_set = {h.lower() for h in exclude}
    buckets: dict[str, list[VideoMetadata]] = {}

    for video in videos:
        for hashtag in video.hashtags:
            if hashtag.lower() in exclude_set:
                continue
            if hashtag not in buckets:
                buckets[hashtag] = []
            buckets[hashtag].append(video)

    return buckets
