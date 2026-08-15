"""Regression tests for continuous entity collision detection."""

from __future__ import annotations

import unittest

import pygame

from entities import Entity


class EntityCollisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.arena = pygame.Rect(0, 0, 500, 300)

    def make_entity(self, pos: tuple[float, float], name: str) -> Entity:
        return Entity(
            pos,
            self.arena,
            name=name,
            body_color=(0, 0, 0),
            limb_color=(0, 0, 0),
        )

    def test_fast_ragdoll_cannot_tunnel_through_another_entity(self) -> None:
        ragdoll = self.make_entity((100, 150), "ragdoll")
        target = self.make_entity((140, 150), "target")
        ragdoll.health = 0
        ragdoll.knockback_velocity.x = 2850
        ragdoll_start = ragdoll.pos.copy()
        target_start = target.pos.copy()

        ragdoll.update_state(1 / 30)

        self.assertGreater(ragdoll.pos.x, target.pos.x)
        self.assertFalse(ragdoll.separate_from(target))
        self.assertTrue(
            ragdoll.resolve_swept_collision(
                target, ragdoll_start, target_start
            )
        )
        self.assertLess(ragdoll.pos.x, target.pos.x)
        self.assertGreater(target.knockback_velocity.x, 0)
        self.assertLess(target.health, target.max_health)

    def test_swept_collision_ignores_a_clear_miss(self) -> None:
        ragdoll = self.make_entity((100, 100), "ragdoll")
        target = self.make_entity((140, 150), "target")
        ragdoll.knockback_velocity.x = 2850
        ragdoll_start = ragdoll.pos.copy()
        target_start = target.pos.copy()

        ragdoll.update_state(1 / 30)

        self.assertFalse(
            ragdoll.resolve_swept_collision(
                target, ragdoll_start, target_start
            )
        )
        self.assertEqual(target.knockback_velocity, pygame.Vector2())
        self.assertEqual(target.health, target.max_health)


if __name__ == "__main__":
    unittest.main()
