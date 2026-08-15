"""Keyboard-controlled entity."""

from __future__ import annotations

import pygame

from .entity import Entity


class Player(Entity):
    def __init__(self, arena: pygame.Rect) -> None:
        super().__init__(
            (arena.centerx, arena.bottom - 116),
            arena,
            name="Player",
            body_color=(71, 139, 204),
            limb_color=(127, 190, 235),
            radius=12,
            max_health=100,
            speed=215,
            backwards_speed=135,
            turn_speed=190,
        )
        self.target: Entity | None = None
        self.locked_on = False
        self.target_indicator_angle = 0.0
        self.defeat_count = 0
        self.base_attack_speed_multiplier = 1.0
        self.powerup_timers = {"fury": 0.0, "haste": 0.0}

    def apply_defeat_progress(self, defeat_count: int, *, heal_growth: bool = False) -> None:
        """Scale player attributes from persistent defeats with diminishing caps."""
        defeat_count = max(0, defeat_count)
        old_max_health = self.max_health
        self.defeat_count = defeat_count
        self.max_health = 100 + min(160, defeat_count * 2.4)
        self.speed = 215 + min(75, defeat_count * 1.4)
        self.backwards_speed = 135 + min(55, defeat_count)
        self.turn_speed = 190 + min(70, defeat_count * 1.2)
        self.damage_scale = 1.0 + min(1.5, defeat_count * 0.025)
        self.base_attack_speed_multiplier = 1.0 + min(1.0, defeat_count * 0.02)
        self.refresh_powerup_stats()
        self.dash_speed = max(480.0, self.speed * 2.75)
        self.fast_turn_speed = max(570.0, self.turn_speed * 3.2)
        if heal_growth:
            self.health = min(
                self.max_health, self.health + self.max_health - old_max_health
            )
        else:
            self.health = self.max_health

    def gain_defeat_strength(self) -> None:
        self.apply_defeat_progress(self.defeat_count + 1, heal_growth=True)

    def refresh_powerup_stats(self) -> None:
        """Combine temporary pickup effects with persistent defeat growth."""
        fury_active = self.powerup_timers.get("fury", 0.0) > 0
        haste_active = self.powerup_timers.get("haste", 0.0) > 0
        self.power_damage_multiplier = 1.5 if fury_active else 1.0
        self.movement_speed_multiplier = 1.32 if haste_active else 1.0
        self.set_attack_speed(
            self.base_attack_speed_multiplier * (1.35 if haste_active else 1.0)
        )

    def apply_powerup(self, kind: str) -> None:
        """Apply an instant heal or refresh a ten-second combat buff."""
        if kind == "health":
            self.health = min(self.max_health, self.health + 35)
        elif kind in self.powerup_timers:
            self.powerup_timers[kind] = max(self.powerup_timers[kind], 10.0)
            self.refresh_powerup_stats()
        else:
            raise ValueError(f"unknown powerup: {kind}")

    def update_powerups(self, dt: float) -> None:
        previous_active = {
            kind: remaining > 0 for kind, remaining in self.powerup_timers.items()
        }
        for kind in self.powerup_timers:
            self.powerup_timers[kind] = max(0.0, self.powerup_timers[kind] - dt)
        if any(
            previous_active[kind] != (remaining > 0)
            for kind, remaining in self.powerup_timers.items()
        ):
            self.refresh_powerup_stats()

    def closest_target(self, targets: list[Entity]) -> Entity | None:
        living_targets = [target for target in targets if target.alive]
        if not living_targets:
            return None
        return min(living_targets, key=lambda target: self.pos.distance_squared_to(target.pos))

    def handle_keydown(self, key: int, targets: list[Entity]) -> None:
        if key == pygame.K_LSHIFT:
            self.locked_on = not self.locked_on
            self.target = self.closest_target(targets) if self.locked_on else None
        elif key == pygame.K_q:
            if self.target is not None and self.target.alive:
                self.strafe_dash(-1)
            else:
                self.fast_turn(-90)
        elif key == pygame.K_e:
            if self.target is not None and self.target.alive:
                self.strafe_dash(1)
            else:
                self.fast_turn(90)
        elif key == pygame.K_j:
            self.start_charging("left")
        elif key == pygame.K_k:
            self.start_charging("right")
        elif key == pygame.K_u:
            self.start_kick("left")
        elif key == pygame.K_i:
            self.start_kick("right")

    def handle_keyup(self, key: int) -> None:
        if key == pygame.K_j:
            self.release_punch("left")
        elif key == pygame.K_k:
            self.release_punch("right")

    def update(
        self,
        dt: float,
        keys: pygame.key.ScancodeWrapper,
        targets: list[Entity],
    ) -> None:
        self.update_powerups(dt)
        if self.locked_on and (
            self.target is None or not self.target.alive or self.target not in targets
        ):
            self.target = self.closest_target(targets)
        elif not self.locked_on:
            self.target = None

        forward = float(keys[pygame.K_w]) - float(keys[pygame.K_s])
        lateral = float(keys[pygame.K_d]) - float(keys[pygame.K_a])
        if self.target is not None:
            self.turn_towards(self.target.pos, dt)
            self.move_axes(forward, 0.0 if self.is_strafe_dashing else lateral, dt)
        else:
            self.turn(0.0 if self.is_fast_turning else lateral, dt)
            self.move(forward, dt)

        self.target_indicator_angle = (self.target_indicator_angle + 125 * dt) % 360
        self.update_state(dt)

    def draw_target_indicator(self, surface: pygame.Surface) -> None:
        """Draw three rotating inward-facing triangles around the locked target."""
        if self.target is None or not self.target.alive:
            return

        color = (255, 205, 68)
        outline = (35, 38, 48)
        orbit_radius = self.target.radius + 23
        for index in range(3):
            direction = self.facing(self.target_indicator_angle + index * 120)
            tangent = direction.rotate(90)
            center = self.target.pos + direction * orbit_radius
            points = [
                center - direction * 8,
                center + direction * 5 + tangent * 5,
                center + direction * 5 - tangent * 5,
            ]
            pygame.draw.polygon(surface, color, points)
            pygame.draw.aalines(surface, outline, True, points)
