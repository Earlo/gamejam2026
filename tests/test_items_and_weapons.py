"""Regression tests for equipment and dropped powerups."""

from __future__ import annotations

import unittest

import pygame

from entities import DroppedItem, Entity, Player, WEAPON_SPECS


class ItemsAndWeaponsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.arena = pygame.Rect(0, 0, 500, 350)
        self.player = Player(self.arena)

    def make_target(self, pos: tuple[float, float]) -> Entity:
        return Entity(
            pos,
            self.arena,
            name="target",
            body_color=(0, 0, 0),
            limb_color=(0, 0, 0),
        )

    def test_weapon_pickups_fill_empty_hands_then_replace_most_worn(self) -> None:
        first = DroppedItem(self.player.pos, weapon_spec=WEAPON_SPECS["club"])
        second = DroppedItem(self.player.pos, weapon_spec=WEAPON_SPECS["sword"])
        replacement = DroppedItem(
            self.player.pos, weapon_spec=WEAPON_SPECS["hammer"]
        )

        self.assertIn("left hand", first.collect(self.player))
        self.assertIn("right hand", second.collect(self.player))
        self.player.weapons["right"].durability = 1
        self.assertIn("right hand", replacement.collect(self.player))
        self.assertEqual(self.player.weapons["left"].name, "CLUB")
        self.assertEqual(self.player.weapons["right"].name, "HAMMER")

    def test_weapon_extends_hit_range_and_spends_durability(self) -> None:
        # Player faces upward. This target is beyond fist contact but inside a
        # sword's segment when the punch reaches its midpoint.
        target = self.make_target((self.player.pos.x, self.player.pos.y - 82))
        self.player.equip_weapon(WEAPON_SPECS["sword"], "left")
        self.player.charge["left"] = self.player.max_charge_time
        self.player.punch_time["left"] = self.player.punch_duration / 2
        durability = self.player.weapons["left"].durability

        self.player.attack((target,))

        self.assertLess(target.health, target.max_health)
        self.assertEqual(
            self.player.weapons["left"].durability, durability - 1
        )

    def test_health_and_temporary_powerups_apply_and_expire(self) -> None:
        self.player.health = 40
        DroppedItem(self.player.pos, powerup="health").collect(self.player)
        self.assertEqual(self.player.health, 75)

        DroppedItem(self.player.pos, powerup="fury").collect(self.player)
        DroppedItem(self.player.pos, powerup="haste").collect(self.player)
        self.assertEqual(self.player.power_damage_multiplier, 1.5)
        self.assertGreater(self.player.movement_speed_multiplier, 1.0)
        self.assertGreater(
            self.player.attack_speed_multiplier,
            self.player.base_attack_speed_multiplier,
        )

        self.player.update_powerups(10.1)
        self.assertEqual(self.player.power_damage_multiplier, 1.0)
        self.assertEqual(self.player.movement_speed_multiplier, 1.0)
        self.assertEqual(
            self.player.attack_speed_multiplier,
            self.player.base_attack_speed_multiplier,
        )

    def test_dropped_items_expire(self) -> None:
        item = DroppedItem((100, 100), powerup="health")
        item.update(item.lifetime)
        self.assertTrue(item.expired)


if __name__ == "__main__":
    unittest.main()
