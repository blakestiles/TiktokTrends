from __future__ import annotations

import re
from collections import Counter

import numpy as np
from loguru import logger
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from scraper.adapter import VideoMetadata

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "be", "as", "this", "that",
    "are", "was", "were", "been", "have", "has", "had", "will", "would",
    "could", "should", "do", "does", "did", "not", "my", "i", "you", "we",
    "he", "she", "they", "me", "him", "her", "us", "them", "so", "if",
    "out", "up", "about", "into", "just", "more", "when", "what", "which",
    "how", "can", "get", "all", "new",
}

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("Loading sentence-transformer model all-MiniLM-L6-v2")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _extract_keywords(captions: list[str], top_n: int = 3) -> list[str]:
    words: list[str] = []
    for caption in captions:
        tokens = re.findall(r"[a-zA-Z]{3,}", caption.lower())
        words.extend(t for t in tokens if t not in STOPWORDS)
    counts = Counter(words)
    return [word for word, _ in counts.most_common(top_n)]


def cluster_topics(
    buckets: dict[str, list[VideoMetadata]],
    similarity_threshold: float,
) -> list[dict]:
    if not buckets:
        return []

    model = _get_model()
    hashtags = list(buckets.keys())

    embeddings_list = []
    for tag in hashtags:
        captions = [v.caption for v in buckets[tag] if v.caption]
        if captions:
            vecs = model.encode(captions, show_progress_bar=False)
            mean_vec = np.mean(vecs, axis=0)
        else:
            mean_vec = model.encode([tag], show_progress_bar=False)[0]
        embeddings_list.append(mean_vec)

    embeddings = np.array(embeddings_list)
    sim_matrix = cosine_similarity(embeddings)

    n = len(hashtags)
    visited = [False] * n
    clusters: list[list[int]] = []

    for i in range(n):
        if visited[i]:
            continue
        cluster = [i]
        visited[i] = True
        for j in range(i + 1, n):
            if not visited[j] and sim_matrix[i][j] >= similarity_threshold:
                cluster.append(j)
                visited[j] = True
        clusters.append(cluster)

    results = []
    for cluster_indices in clusters:
        primary_idx = cluster_indices[0]
        primary_hashtag = hashtags[primary_idx]
        related_hashtags = [hashtags[idx] for idx in cluster_indices[1:]]

        all_videos: list[VideoMetadata] = []
        for idx in cluster_indices:
            all_videos.extend(buckets[hashtags[idx]])

        all_captions = [v.caption for v in all_videos if v.caption]
        keywords = _extract_keywords(all_captions, top_n=3)
        topic_label = " + ".join(keywords) if keywords else primary_hashtag.lstrip("#")

        results.append({
            "topic_label": topic_label,
            "primary_hashtag": primary_hashtag,
            "related_hashtags": related_hashtags,
            "videos": all_videos,
        })

    logger.info(f"Clustered {len(hashtags)} hashtag buckets into {len(results)} topic clusters")
    return results
