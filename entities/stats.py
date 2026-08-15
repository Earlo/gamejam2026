"""Deterministic article-length-based brawler stats."""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Mapping


STAT_KEYS = ("health", "speed", "damage", "turn", "aggression")


def enemy_point_budget(article_length: int) -> int:
    """Longer articles grant more points, with a gentle late-game taper."""
    return 5 + min(35, int(math.sqrt(max(0, article_length) / 300)))


def allocate_enemy_stats(name: str, article_length: int) -> dict[str, int]:
    """Distribute a person's budget into a stable, non-uniform build."""
    budget = enemy_point_budget(article_length)
    seed_material = f"{name}\0{article_length}".encode("utf-8")
    seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big")
    rng = random.Random(seed)
    weights = [rng.uniform(0.35, 1.65) ** 2 for _ in STAT_KEYS]
    points = {stat: 1 for stat in STAT_KEYS}
    for _ in range(budget - len(STAT_KEYS)):
        selected = rng.choices(STAT_KEYS, weights=weights, k=1)[0]
        points[selected] += 1
    return points


def normalized_stats(value: object, name: str, article_length: int) -> dict[str, int]:
    """Validate saved allocations or regenerate them deterministically."""
    if isinstance(value, Mapping):
        points = {
            stat: max(0, int(value.get(stat, 0)))
            for stat in STAT_KEYS
            if isinstance(value.get(stat, 0), (int, float))
        }
        if set(points) == set(STAT_KEYS) and sum(points.values()) > 0:
            return points
    return allocate_enemy_stats(name, article_length)
