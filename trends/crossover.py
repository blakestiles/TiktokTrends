from __future__ import annotations

from scraper.adapter import TrendRecord


def detect_crossovers(trends_by_category: dict[str, list[TrendRecord]]) -> list[TrendRecord]:
    hashtag_to_trends: dict[str, list[TrendRecord]] = {}

    for category, trends in trends_by_category.items():
        for trend in trends:
            tag = trend.primary_hashtag
            if tag not in hashtag_to_trends:
                hashtag_to_trends[tag] = []
            hashtag_to_trends[tag].append(trend)

    crossover_trends: list[TrendRecord] = []

    for tag, trend_list in hashtag_to_trends.items():
        if len(trend_list) < 2:
            continue
        categories = list({t.category for t in trend_list})
        for trend in trend_list:
            other_cats = [c for c in categories if c != trend.category]
            updated = trend.model_copy(update={"crossover_categories": other_cats})
            crossover_trends.append(updated)

    return crossover_trends
