"""AI-controlled entity using the same actions as the player."""

from __future__ import annotations

import pygame

from .entity import Entity


class Enemy(Entity):
    def __init__(
        self,
        pos: pygame.Vector2 | tuple[float, float],
        name: str,
        arena: pygame.Rect,
        *,
        radius: int = 12,
        max_health: float = 38,
        speed: float = 68,
        turn_speed: float = 145,
        damage_scale: float = 0.72,
        aggression: int = 1,
        stat_points: dict[str, int] | None = None,
        article_length: int = 0,
        boss: bool = False,
    ) -> None:
        self.boss = boss
        self.aggression = aggression
        self.stat_points = dict(stat_points or {})
        self.article_length = article_length
        self.cooldown_factor = max(0.52, 1.0 - aggression * 0.045)
        super().__init__(
            pos,
            arena,
            name=name,
            body_color=(137, 45, 50) if boss else (202, 82, 75),
            limb_color=(185, 72, 72) if boss else (224, 119, 103),
            radius=radius,
            max_health=max_health,
            speed=speed,
            turn_speed=turn_speed,
            damage_scale=damage_scale,
        )
        self.action_cooldown = 0.35 * self.cooldown_factor
        self.charging_side: str | None = None
        self.charge_goal = 0.0
        self.next_side = "left"
        self.action_count = 0
        self.target: Entity | None = None
        self.strafe_direction = -1 if sum(map(ord, name)) % 2 else 1
        self.strafe_timer = 0.9 + (sum(map(ord, name)) % 5) * 0.13
        self.last_target_pos: pygame.Vector2 | None = None

    def update(self, dt: float, target: Entity) -> None:
        """Chase and choose actions; Entity performs all physical mechanics."""
        self.target = target
        self.update_state(dt)
        if not self.alive:
            self.target = None
            return
        self.action_cooldown = max(0.0, self.action_cooldown - dt)
        self.turn_towards(target.pos, dt)

        target_lateral_speed = 0.0
        if self.last_target_pos is not None and dt > 0:
            target_motion = target.pos - self.last_target_pos
            target_lateral_speed = abs(
                target_motion.dot(self.forward.rotate(90)) / dt
            )
        self.last_target_pos = target.pos.copy()

        self.strafe_timer -= dt
        if self.strafe_timer <= 0:
            self.strafe_direction *= -1
            self.strafe_timer = (1.15 if self.boss else 1.55) * self.cooldown_factor

        distance = self.pos.distance_to(target.pos)
        preferred_distance = self.radius + target.radius + 29
        forward_amount = 0.0
        if distance > preferred_distance + 8:
            forward_amount = 1.0
        elif distance < preferred_distance - 8:
            forward_amount = -0.45

        attack_distance = self.radius + target.radius + 52
        strafe_amount = 0.72 * self.strafe_direction if distance < attack_distance + 45 else 0.0
        if self.is_strafe_dashing:
            strafe_amount = 0.0
        self.move_axes(forward_amount, strafe_amount, dt)

        if self.charging_side is not None:
            side = self.charging_side
            if self.charge[side] >= self.charge_goal:
                self.release_punch(side)
                self.charging_side = None
                self.action_cooldown = 0.72 * self.cooldown_factor
            return

        if distance > attack_distance or self.action_cooldown > 0:
            return

        side = self.next_side
        self.next_side = "right" if side == "left" else "left"
        self.action_count += 1

        if self.action_count % 5 == 0 and self.strafe_dash(self.strafe_direction, 52):
            self.action_cooldown = 0.38 * self.cooldown_factor
            return

        target_is_strafing = (
            target_lateral_speed >= 65 and distance <= attack_distance + 16
        )
        if target_is_strafing or self.action_count % 3 == 0:
            self.start_kick(side)
            self.action_cooldown = 0.78 * self.cooldown_factor
        else:
            self.start_charging(side)
            self.charging_side = side
            self.charge_goal = 0.5 if self.boss else 0.28

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        super().draw(surface, font, show_status=True)
