"""Deterministic article-length-based brawler stats."""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Mapping


STAT_KEYS = (
    "health",
    "speed",
    "damage",
    "turn",
    "aggression",
    "attack_speed",
)

THREAT_LABELS = ("SCRAPPY", "TOUGH", "FIERCE", "BRUTAL", "LEGENDARY", "BOSS")


def enemy_point_budget(article_length: int) -> int:
    """Longer articles grant more points, with a gentle late-game taper."""
    return 6 + min(49, int(math.sqrt(max(0, article_length) / 140)))


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


def enemy_threat_level(stat_points: Mapping[str, int], *, boss: bool = False) -> int:
    """Return a visible 0-5 threat tier from an enemy's total point budget."""
    if boss:
        return 5
    total = sum(max(0, int(stat_points.get(stat, 0))) for stat in STAT_KEYS)
    return min(4, max(0, (total - len(STAT_KEYS)) // 10))


def enemy_threat_label(stat_points: Mapping[str, int], *, boss: bool = False) -> str:
    return THREAT_LABELS[enemy_threat_level(stat_points, boss=boss)]


def enemy_combat_stats(
    stat_points: Mapping[str, int], *, boss: bool = False
) -> dict[str, float | int]:
    """Turn point allocations and threat tier into final in-game attributes.

    Individual allocations still define each fighter's specialty. The total-point
    tier adds a smaller bonus across the whole build, so a visibly meaner enemy is
    reliably more dangerous instead of merely being specialized differently.
    """
    points = {stat: max(0, int(stat_points.get(stat, 0))) for stat in STAT_KEYS}
    threat = enemy_threat_level(points, boss=boss)
    regular_threat = min(4, threat)
    boss_health = 1.35 if boss else 1.0
    boss_damage = 1.25 if boss else 1.0
    boss_speed = 1.08 if boss else 1.0
    return {
        "threat_level": threat,
        "radius": 30 if boss else 11 + regular_threat * 2,
        "max_health": (42 + points["health"] * 8)
        * (1.0 + regular_threat * 0.13)
        * boss_health,
        "speed": (58 + points["speed"] * 5.5)
        * (1.0 + regular_threat * 0.018)
        * boss_speed,
        "turn_speed": (130 + points["turn"] * 10)
        * (1.0 + regular_threat * 0.025),
        "damage_scale": (0.72 + points["damage"] * 0.09)
        * (1.0 + regular_threat * 0.11)
        * boss_damage,
        "aggression": points["aggression"] + regular_threat + (2 if boss else 0),
        "attack_speed": points["attack_speed"]
        + regular_threat // 2
        + (2 if boss else 0),
    }


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
