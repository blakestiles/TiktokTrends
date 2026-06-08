from __future__ import annotations

from scraper.adapter import VideoMetadata

CATEGORY_CONFIG: dict[str, dict] = {
    "games": {
        "hashtags": [
            "#gaming", "#gamer", "#videogames", "#gameplay", "#gamedev",
            "#pcgaming", "#consolegaming", "#esports", "#streamer", "#twitch",
        ],
        "keywords": [
            "game", "gaming", "gamer", "play", "level", "boss", "quest",
            "multiplayer", "fps", "rpg", "mmo", "indie", "speedrun", "mod",
        ],
    },
    "card_games": {
        "hashtags": [
            "#cardgames", "#tcg", "#mtg", "#magicthegathering", "#yugioh",
            "#pokemontcg", "#hearthstone", "#lorcana", "#flesh_and_blood",
            "#tradingcards",
        ],
        "keywords": [
            "card", "deck", "pack", "rare", "legendary", "draft", "sealed",
            "booster", "foil", "trading", "collectible", "tcg", "tournament",
            "combo",
        ],
    },
    "games_marketing": {
        "hashtags": [
            "#gametrailer", "#newgame", "#gamesrelease", "#indiegame", "#gameannouncement",
            "#betaaccess", "#earlyaccess", "#gamespreview", "#gamelaunch", "#freegame",
        ],
        "keywords": [
            "launch", "release", "announcement", "trailer", "beta", "early access",
            "free to play", "download", "pre-order", "exclusive", "demo", "preview",
            "sponsor", "ad",
        ],
    },
}


def classify_video(video: VideoMetadata, config: dict) -> dict[str, float]:
    """
    Score = weighted combination of:
      - hashtag_hit: 1.0 if any category hashtag matches, scaled by match count (capped at 1.0)
      - keyword_hit: fraction of caption words that match category keywords (capped at 1.0)
    This means a single hashtag match produces a strong signal.
    """
    scores: dict[str, float] = {}
    caption_lower = video.caption.lower() if video.caption else ""
    hashtag_set = {h.lower() for h in video.hashtags}

    cat_cfg = config if config else CATEGORY_CONFIG

    for category, cfg in cat_cfg.items():
        cat_hashtags = [h.lower() for h in cfg.get("hashtags", [])]
        cat_keywords = [k.lower() for k in cfg.get("keywords", [])]

        if cat_hashtags:
            hashtag_matches = sum(1 for h in cat_hashtags if h in hashtag_set)
            hashtag_score = min(1.0, hashtag_matches * 0.5)
        else:
            hashtag_score = 0.0

        if cat_keywords:
            keyword_matches = sum(1 for k in cat_keywords if k in caption_lower)
            keyword_score = min(1.0, keyword_matches * 0.25)
        else:
            keyword_score = 0.0

        scores[category] = hashtag_score * 0.7 + keyword_score * 0.3

    return scores


def get_primary_category(scores: dict[str, float], min_score: float) -> str | None:
    if not scores:
        return None
    best = max(scores, key=lambda k: scores[k])
    if scores[best] >= min_score:
        return best
    return None
