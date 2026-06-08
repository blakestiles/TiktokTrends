from __future__ import annotations

import numpy as np

from scraper.adapter import TrendRecord


def compute_momentum(trend: TrendRecord, weights: dict) -> float:
    w_velocity = weights.get("velocity", 0.5)
    w_rank = weights.get("rank", 0.3)
    w_engagement = weights.get("engagement", 0.2)

    velocity_component = min(max(trend.velocity_pct / 100.0, 0.0), 1.0)

    if len(trend.rank_history) >= 2:
        rank_prev = trend.rank_history[-2]
        rank_curr = trend.rank_history[-1]
        rank_improvement = rank_prev - rank_curr
        rank_component = min(max((rank_improvement + 20) / 40.0, 0.0), 1.0)
    else:
        rank_component = 0.5

    if len(trend.engagement_history) >= 2:
        eng_prev = trend.engagement_history[-2]
        eng_curr = trend.engagement_history[-1]
        if eng_prev > 0:
            growth_rate = (eng_curr - eng_prev) / eng_prev
            engagement_component = min(max((growth_rate + 0.5) / 1.0, 0.0), 1.0)
        else:
            engagement_component = 0.5
    else:
        engagement_component = 0.5

    score = (
        w_velocity * velocity_component
        + w_rank * rank_component
        + w_engagement * engagement_component
    )
    return min(max(score, 0.0), 1.0)


def predict_peak(trend: TrendRecord) -> str | None:
    if len(trend.engagement_history) < 3:
        return None

    history = np.array(trend.engagement_history, dtype=float)
    x = np.arange(len(history))
    coeffs = np.polyfit(x, history, 1)
    slope = coeffs[0]

    max_val = float(np.max(history))
    if max_val == 0:
        return None

    if slope <= 0 or abs(slope) < 0.05 * max_val:
        return _week_offset(trend.last_seen, 0)

    current_growth_rate = slope / (history[-1] if history[-1] > 0 else 1)
    if current_growth_rate < 0.1:
        return _week_offset(trend.last_seen, 0)

    weeks_to_slow = int((current_growth_rate - 0.1) / (0.1 + 1e-9)) + 1
    weeks_to_slow = min(weeks_to_slow, 12)
    return _week_offset(trend.last_seen, weeks_to_slow)


def _week_offset(week_str: str, offset: int) -> str:
    try:
        from datetime import date, timedelta
        parts = week_str.split("-W")
        year = int(parts[0])
        week = int(parts[1])
        monday = date.fromisocalendar(year, week, 1)
        target = monday + timedelta(weeks=offset)
        iso = target.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    except Exception:
        return week_str
