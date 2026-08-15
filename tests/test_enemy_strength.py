"""Regression tests for enemy threat scaling and stable appearances."""

from __future__ import annotations

import unittest

import pygame

from entities import Enemy, STAT_KEYS, enemy_combat_stats, enemy_threat_level


def balanced_points(total: int) -> dict[str, int]:
    points = {stat: total // len(STAT_KEYS) for stat in STAT_KEYS}
    for stat in STAT_KEYS[: total % len(STAT_KEYS)]:
        points[stat] += 1
    return points


class EnemyStrengthTests(unittest.TestCase):
    def test_point_budgets_map_to_increasing_threat_tiers(self) -> None:
        for expected_tier, total in enumerate((6, 16, 26, 36, 46)):
            with self.subTest(total=total):
                self.assertEqual(
                    enemy_threat_level(balanced_points(total)), expected_tier
                )

    def test_higher_balanced_tiers_are_stronger_across_combat_stats(self) -> None:
        previous = enemy_combat_stats(balanced_points(6))
        for total in (16, 26, 36, 46):
            current = enemy_combat_stats(balanced_points(total))
            with self.subTest(total=total):
                for stat in ("max_health", "speed", "turn_speed", "damage_scale"):
                    self.assertGreater(current[stat], previous[stat])
                self.assertGreater(current["aggression"], previous["aggression"])
                self.assertGreaterEqual(
                    current["attack_speed"], previous["attack_speed"]
                )
            previous = current

    def test_boss_flag_guarantees_boss_threat_and_bonus(self) -> None:
        points = balanced_points(6)
        regular = enemy_combat_stats(points)
        boss = enemy_combat_stats(points, boss=True)
        self.assertEqual(boss["threat_level"], 5)
        self.assertGreater(boss["max_health"], regular["max_health"])
        self.assertGreater(boss["damage_scale"], regular["damage_scale"])
        self.assertGreater(boss["speed"], regular["speed"])

    def test_enemy_appearance_is_stable_and_name_derived(self) -> None:
        arena = pygame.Rect(0, 0, 300, 200)
        points = balanced_points(26)
        first = Enemy((50, 50), "Ada Lovelace", arena, stat_points=points)
        repeat = Enemy((50, 50), "Ada Lovelace", arena, stat_points=points)
        other = Enemy((50, 50), "Grace Hopper", arena, stat_points=points)
        self.assertEqual(first.appearance_id, repeat.appearance_id)
        self.assertNotEqual(first.appearance_id, other.appearance_id)
        self.assertEqual(first.threat_level, 2)


if __name__ == "__main__":
    unittest.main()
