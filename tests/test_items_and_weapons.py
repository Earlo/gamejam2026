"""Regression tests for equipment and dropped powerups."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pygame

from entities import DroppedItem, Enemy, Entity, Player, WEAPON_SPECS
from game import ARENA, Game


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
            self.player.pos, weapon_spec=WEAPON_SPECS["gun"]
        )

        self.assertIn("left hand", first.collect(self.player))
        self.assertIn("right hand", second.collect(self.player))
        self.player.weapons["right"].durability = 1
        self.assertIn("right hand", replacement.collect(self.player))
        self.assertEqual(self.player.weapons["left"].name, "CLUB")
        self.assertEqual(self.player.weapons["right"].name, "GUN")

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

    def test_club_sweeps_while_sword_keeps_stabbing_forward(self) -> None:
        self.player.equip_weapon(WEAPON_SPECS["club"], "left")
        self.player.punch_time["left"] = self.player.punch_duration
        early_swing = self.player.weapon_direction("left")
        self.player.punch_time["left"] = self.player.punch_duration * 0.5
        middle_swing = self.player.weapon_direction("left")
        self.player.punch_time["left"] = 0.0001
        late_swing = self.player.weapon_direction("left")

        def signed_angle(direction: pygame.Vector2) -> float:
            angle = self.player.forward.angle_to(direction)
            return (angle + 180) % 360 - 180

        self.assertAlmostEqual(
            signed_angle(early_swing), 150, delta=0.1
        )
        self.assertAlmostEqual(
            signed_angle(middle_swing), 0, delta=0.1
        )
        self.assertAlmostEqual(
            signed_angle(late_swing), -150, delta=0.2
        )
        self.assertLess(early_swing.x * late_swing.x, 0)

        self.player.equip_weapon(WEAPON_SPECS["sword"], "left")
        self.assertEqual(self.player.weapon_direction("left"), self.player.forward)

    def test_gun_hits_at_range_and_spends_ammo(self) -> None:
        self.player.equip_weapon(WEAPON_SPECS["gun"], "left")
        self.player.charge["left"] = self.player.max_charge_time
        self.player.punch_time["left"] = self.player.punch_duration / 2
        muzzle = self.player.weapon_tip("left")
        target = self.make_target((muzzle.x, muzzle.y - 145))
        ammo = self.player.weapons["left"].durability

        self.player.attack((target,))

        self.assertLess(target.health, target.max_health)
        self.assertEqual(self.player.weapons["left"].durability, ammo - 1)
        self.assertGreater(self.player.shot_tracer_time["left"], 0)

    def test_unarmed_enemy_usually_drops_nothing(self) -> None:
        game = Game.__new__(Game)
        game.player = Player(ARENA)
        game.dropped_items = []
        enemy = Enemy((200, 200), "Unarmed", ARENA, threat_level=0)

        with patch("game.random.random", return_value=0.99):
            game.drop_enemy_loot(enemy)

        self.assertEqual(game.dropped_items, [])

    def test_enemy_drops_the_weapon_and_durability_it_used(self) -> None:
        game = Game.__new__(Game)
        game.player = Player(ARENA)
        game.dropped_items = []
        enemy = Enemy((200, 200), "Armed", ARENA, threat_level=1)
        enemy.equip_weapon(WEAPON_SPECS["sword"], "right", durability=3)

        game.drop_enemy_loot(enemy)

        self.assertEqual(len(game.dropped_items), 1)
        drop = game.dropped_items[0]
        self.assertEqual(drop.weapon_spec.name, "SWORD")
        self.assertEqual(drop.weapon_durability, 3)

    def test_armed_enemy_selects_and_fires_its_gun(self) -> None:
        target = Player(self.arena)
        target.pos.update(250, 70)
        enemy = Enemy((250, 270), "Gunner", self.arena, threat_level=2)
        enemy.equip_weapon(WEAPON_SPECS["gun"], "left")
        enemy.action_cooldown = 0
        starting_ammo = enemy.weapons["left"].durability

        enemy.update(0.01, target)
        self.assertEqual(enemy.charging_side, "left")
        enemy.update(0.30, target)
        enemy.attack((target,))

        self.assertLess(target.health, target.max_health)
        self.assertEqual(enemy.weapons["left"].durability, starting_ammo - 1)

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
