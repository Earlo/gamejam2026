"""Shared movement, combat, and rendering for every brawler entity."""

from __future__ import annotations

import math
from collections.abc import Iterable

import pygame


class Entity:
    """A ball-bodied brawler with two hands, two feet, and shared combat rules."""

    SIDES = ("left", "right")
    punch_duration = 0.24
    kick_duration = 0.28
    max_charge_time = 0.75

    def __init__(
        self,
        pos: pygame.Vector2 | tuple[float, float],
        arena: pygame.Rect,
        *,
        name: str,
        body_color: tuple[int, int, int],
        limb_color: tuple[int, int, int],
        radius: int = 12,
        max_health: float = 100,
        speed: float = 215,
        backwards_speed: float | None = None,
        turn_speed: float = 190,
        damage_scale: float = 1.0,
    ) -> None:
        self.pos = pygame.Vector2(pos)
        self.arena = arena.copy()
        self.name = name
        self.body_color = body_color
        self.limb_color = limb_color
        self.radius = radius
        self.hand_radius = max(5, round(radius * 0.42))
        self.max_health = float(max_health)
        self.health = float(max_health)
        self.speed = speed
        self.backwards_speed = backwards_speed if backwards_speed is not None else speed
        self.turn_speed = turn_speed
        self.damage_scale = damage_scale

        self.angle = 0.0
        self.flash = 0.0
        self.charging = {side: False for side in self.SIDES}
        self.charge = {side: 0.0 for side in self.SIDES}
        self.punch_time = {side: 0.0 for side in self.SIDES}
        self.punch_hits = {side: set() for side in self.SIDES}
        self.kick_time = {side: 0.0 for side in self.SIDES}
        self.kick_cooldown = {side: 0.0 for side in self.SIDES}
        self.kick_hits = {side: set() for side in self.SIDES}
        self.dash_cooldown = 0.0
        self.dash_time = 0.0
        self.dash_direction = 0.0
        self.dash_speed = max(480.0, speed * 2.75)
        self.fast_turn_remaining = 0.0
        self.fast_turn_speed = max(570.0, turn_speed * 3.2)

    @staticmethod
    def clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    @staticmethod
    def facing(angle: float) -> pygame.Vector2:
        """Return a screen-space direction where zero degrees points upward."""
        return pygame.Vector2(0, -1).rotate(angle)

    @staticmethod
    def draw_oriented_oval(
        surface: pygame.Surface,
        center: pygame.Vector2,
        along: pygame.Vector2,
        length: float,
        width: float,
        color: tuple[int, int, int],
        outline: tuple[int, int, int],
    ) -> None:
        side = along.rotate(90)
        points = []
        for index in range(18):
            radians = math.tau * index / 18
            point = center + along * math.cos(radians) * length / 2
            point += side * math.sin(radians) * width / 2
            points.append(point)
        pygame.draw.polygon(surface, color, points)
        pygame.draw.aalines(surface, outline, True, points)

    @property
    def forward(self) -> pygame.Vector2:
        return self.facing(self.angle)

    @property
    def alive(self) -> bool:
        return self.health > 0

    def keep_in_arena(self) -> None:
        self.pos.x = self.clamp(
            self.pos.x, self.arena.left + self.radius, self.arena.right - self.radius
        )
        self.pos.y = self.clamp(
            self.pos.y, self.arena.top + self.radius, self.arena.bottom - self.radius
        )

    def move(self, amount: float, dt: float) -> None:
        """Move on the entity's facing axis; negative amounts move backward."""
        self.move_axes(amount, 0.0, dt)

    def move_axes(self, forward_amount: float, strafe_amount: float, dt: float) -> None:
        """Move forward/backward and sideways without a diagonal speed boost."""
        movement = pygame.Vector2(strafe_amount, forward_amount)
        if movement.length_squared() > 1:
            movement = movement.normalize()
        forward_speed = self.speed if movement.y >= 0 else self.backwards_speed
        self.pos += self.forward * movement.y * forward_speed * dt
        self.pos += self.forward.rotate(90) * movement.x * self.speed * dt
        self.keep_in_arena()

    @property
    def is_strafe_dashing(self) -> bool:
        return self.dash_time > 0

    @property
    def is_fast_turning(self) -> bool:
        return abs(self.fast_turn_remaining) > 0

    def strafe_dash(self, amount: float, distance: float = 76) -> bool:
        """Begin a short, fast sideways movement instead of teleporting."""
        if self.dash_cooldown > 0:
            return False
        self.dash_direction = -1.0 if amount < 0 else 1.0
        self.dash_time = distance / self.dash_speed
        self.dash_cooldown = self.dash_time + 0.28
        return True

    def turn(self, amount: float, dt: float) -> None:
        self.angle = (self.angle + amount * self.turn_speed * dt) % 360

    def fast_turn(self, degrees: float) -> bool:
        """Begin a boosted turn that travels through, rather than jumps, 90 degrees."""
        if self.is_fast_turning:
            return False
        self.fast_turn_remaining = degrees
        return True

    def turn_towards(self, target: pygame.Vector2, dt: float) -> None:
        offset = target - self.pos
        if offset.length_squared() <= 0:
            return
        target_angle = math.degrees(math.atan2(offset.x, -offset.y))
        difference = (target_angle - self.angle + 180) % 360 - 180
        maximum = self.turn_speed * dt
        self.angle = (self.angle + self.clamp(difference, -maximum, maximum)) % 360

    def separate_from(self, other: Entity) -> bool:
        """Resolve circular body overlap between this entity and another."""
        offset = other.pos - self.pos
        minimum_distance = self.radius + other.radius
        distance_squared = offset.length_squared()
        if distance_squared >= minimum_distance * minimum_distance:
            return False

        if distance_squared == 0:
            # A stable fallback for entities spawned at exactly the same position.
            offset = pygame.Vector2(1, 0)
            distance = 0.0
        else:
            distance = math.sqrt(distance_squared)
            offset /= distance

        correction = offset * ((minimum_distance - distance) / 2 + 0.01)
        self.pos -= correction
        other.pos += correction
        self.keep_in_arena()
        other.keep_in_arena()
        return True

    def start_charging(self, side: str) -> None:
        if self.punch_time[side] <= 0 and not self.charging[side]:
            self.charge[side] = 0.0
            self.charging[side] = True

    def release_punch(self, side: str) -> None:
        if not self.charging[side]:
            return
        self.charging[side] = False
        self.charge[side] = max(0.08, self.charge[side])
        self.punch_time[side] = self.punch_duration
        self.punch_hits[side].clear()

    def start_kick(self, side: str) -> None:
        if self.kick_cooldown[side] > 0:
            return
        self.kick_time[side] = self.kick_duration
        self.kick_cooldown[side] = 0.48
        self.kick_hits[side].clear()

    def update_state(self, dt: float) -> None:
        """Advance timers shared by human- and AI-controlled entities."""
        for side in self.SIDES:
            if self.charging[side]:
                self.charge[side] = min(
                    self.max_charge_time, self.charge[side] + dt
                )

            previous_punch_time = self.punch_time[side]
            self.punch_time[side] = max(0.0, previous_punch_time - dt)
            if self.punch_time[side] <= 0 < previous_punch_time:
                self.charge[side] = 0.0

            self.kick_time[side] = max(0.0, self.kick_time[side] - dt)
            self.kick_cooldown[side] = max(0.0, self.kick_cooldown[side] - dt)

        if self.is_fast_turning:
            turn_step = math.copysign(
                min(abs(self.fast_turn_remaining), self.fast_turn_speed * dt),
                self.fast_turn_remaining,
            )
            self.angle = (self.angle + turn_step) % 360
            self.fast_turn_remaining -= turn_step

        if self.is_strafe_dashing:
            dash_dt = min(dt, self.dash_time)
            self.pos += (
                self.forward.rotate(90)
                * self.dash_direction
                * self.dash_speed
                * dash_dt
            )
            self.dash_time = max(0.0, self.dash_time - dash_dt)
            self.keep_in_arena()

        self.dash_cooldown = max(0.0, self.dash_cooldown - dt)
        self.flash = max(0.0, self.flash - dt)

    def hand_position(self, side_name: str) -> pygame.Vector2:
        right = self.forward.rotate(90)
        side = -right if side_name == "left" else right
        position = self.pos + side * (self.radius + self.hand_radius)

        if self.charging[side_name]:
            ratio = self.charge[side_name] / self.max_charge_time
            position -= self.forward * (5 + 10 * ratio)
        elif self.punch_time[side_name] > 0:
            ratio = self.charge[side_name] / self.max_charge_time
            target = self.pos + self.forward * (self.radius + 16 + 40 * ratio)
            target += side * self.hand_radius
            progress = 1 - self.punch_time[side_name] / self.punch_duration
            position += (target - position) * math.sin(progress * math.pi)
        return position

    def foot_position(self, side_name: str) -> pygame.Vector2:
        right = self.forward.rotate(90)
        side = -right if side_name == "left" else right
        position = self.pos - self.forward * (self.radius + 8)
        position += side * (self.radius + 1)
        if self.kick_time[side_name] > 0:
            progress = 1 - self.kick_time[side_name] / self.kick_duration
            position += self.forward * math.sin(progress * math.pi) * (self.radius + 51)
        return position

    def attack(self, targets: Iterable[Entity]) -> None:
        """Resolve active hand and foot attacks against other entities."""
        targets = tuple(target for target in targets if target is not self and target.alive)
        for side in self.SIDES:
            if self.punch_time[side] > 0:
                hand = self.hand_position(side)
                power_ratio = self.charge[side] / self.max_charge_time
                for target in targets:
                    target_id = id(target)
                    if target_id in self.punch_hits[side]:
                        continue
                    if hand.distance_to(target.pos) <= self.hand_radius + target.radius:
                        damage = (10 + 22 * power_ratio) * self.damage_scale
                        knockback = (10 + 25 * power_ratio) * self.damage_scale
                        target.take_damage(damage, self.forward * knockback)
                        self.punch_hits[side].add(target_id)

            if self.kick_time[side] > 0:
                foot = self.foot_position(side)
                for target in targets:
                    target_id = id(target)
                    if target_id in self.kick_hits[side]:
                        continue
                    if foot.distance_to(target.pos) <= self.radius + 1 + target.radius:
                        target.take_damage(16 * self.damage_scale, self.forward * 30)
                        self.kick_hits[side].add(target_id)

    def take_damage(self, amount: float, knockback: pygame.Vector2 | None = None) -> None:
        self.health = max(0.0, self.health - amount)
        self.flash = 0.11
        if knockback is not None:
            self.pos += knockback
            self.keep_in_arena()

    def fist_color(self, side: str) -> tuple[int, int, int]:
        ratio = self.clamp(self.charge[side] / self.max_charge_time, 0, 1)
        charged_color = (255, 231, 125)
        return tuple(
            round(charged * ratio + normal * (1 - ratio))
            for normal, charged in zip(self.limb_color, charged_color)
        )

    def draw(
        self,
        surface: pygame.Surface,
        font: pygame.font.Font | None = None,
        *,
        show_status: bool = False,
    ) -> None:
        """Draw the shared ball body, ball hands, oval feet, face, and status."""
        outline = (35, 38, 48)
        hit_color = (255, 231, 125)
        right = self.forward.rotate(90)

        for side in self.SIDES:
            self.draw_oriented_oval(
                surface,
                self.foot_position(side),
                self.forward,
                self.radius * 1.8,
                self.radius * 1.05,
                self.limb_color,
                outline,
            )

        pygame.draw.circle(surface, outline, self.pos, self.radius + 3)
        pygame.draw.circle(
            surface, hit_color if self.flash else self.body_color, self.pos, self.radius
        )

        eye_base = self.pos + self.forward * self.radius * 0.45
        eye_offset = max(4, self.radius * 0.34)
        eye_radius = max(2, round(self.radius * 0.2))
        for eye_side in (-1, 1):
            eye = eye_base + right * eye_side * eye_offset
            pygame.draw.circle(surface, (250, 250, 245), eye, eye_radius)
            pygame.draw.circle(surface, outline, eye + self.forward * 2, max(1, eye_radius // 2))

        for side in self.SIDES:
            hand = self.hand_position(side)
            pygame.draw.circle(surface, outline, hand, self.hand_radius + 2)
            pygame.draw.circle(surface, self.fist_color(side), hand, self.hand_radius)

        if show_status and font is not None:
            bar = pygame.Rect(0, 0, self.radius * 2, 6)
            bar.midbottom = (round(self.pos.x), round(self.pos.y - self.radius - 8))
            pygame.draw.rect(surface, outline, bar, border_radius=3)
            fill = bar.inflate(-2, -2)
            fill.width = round(fill.width * self.health / self.max_health)
            pygame.draw.rect(surface, (102, 196, 114), fill, border_radius=2)

            label = font.render(self.name, True, outline)
            surface.blit(
                label,
                label.get_rect(midtop=(self.pos.x, self.pos.y + self.radius + 7)),
            )
