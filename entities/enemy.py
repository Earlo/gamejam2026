"""AI-controlled entity using the same actions as the player."""

from __future__ import annotations

import hashlib

import pygame

from .entity import Entity
from .stats import STAT_KEYS, enemy_threat_level


class Enemy(Entity):
    PALETTES = (
        ((202, 82, 75), (224, 119, 103), (255, 190, 92)),
        ((178, 72, 137), (218, 116, 174), (255, 199, 88)),
        ((116, 82, 174), (166, 128, 211), (238, 181, 80)),
        ((52, 141, 108), (98, 181, 140), (246, 177, 73)),
        ((203, 112, 47), (232, 154, 78), (255, 220, 110)),
        ((149, 74, 62), (199, 113, 91), (242, 177, 94)),
        ((105, 137, 57), (154, 180, 91), (249, 187, 77)),
        ((64, 139, 150), (106, 183, 187), (247, 176, 87)),
    )

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
        attack_speed: int = 1,
        threat_level: int | None = None,
        stat_points: dict[str, int] | None = None,
        article_length: int = 0,
        boss: bool = False,
    ) -> None:
        self.boss = boss
        self.aggression = aggression
        self.attack_speed_points = attack_speed
        self.stat_points = dict(stat_points or {})
        if boss:
            threat_level = 5
        elif threat_level is None:
            threat_level = enemy_threat_level(self.stat_points)
        self.threat_level = max(0, min(5, threat_level))
        self.article_length = article_length
        appearance = hashlib.sha256(name.casefold().encode("utf-8")).digest()
        self.appearance_id = (
            appearance[0] % len(self.PALETTES),
            appearance[1] % 6,
            appearance[2] % 4,
        )
        self.marking_style = self.appearance_id[1]
        self.detail_variant = self.appearance_id[2]
        self.dominant_stat = max(
            STAT_KEYS,
            key=lambda stat: (self.stat_points.get(stat, 0), -STAT_KEYS.index(stat)),
        )
        palette = self.PALETTES[self.appearance_id[0]]
        menace_darkening = 1.0 - min(4, self.threat_level) * 0.055
        body_color = self.tint(palette[0], menace_darkening)
        limb_color = self.tint(palette[1], menace_darkening)
        self.accent_color = palette[2]
        if boss:
            body_color = (105, 29, 37)
            limb_color = (164, 57, 61)
            self.accent_color = (240, 176, 54)
        self.cooldown_factor = max(0.42, 1.0 - attack_speed * 0.06)
        super().__init__(
            pos,
            arena,
            name=name,
            body_color=body_color,
            limb_color=limb_color,
            radius=radius,
            max_health=max_health,
            speed=speed,
            turn_speed=turn_speed,
            damage_scale=damage_scale,
            attack_speed_multiplier=1.0 + attack_speed * 0.055,
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

    @staticmethod
    def tint(
        color: tuple[int, int, int], factor: float
    ) -> tuple[int, int, int]:
        return tuple(max(0, min(255, round(channel * factor))) for channel in color)

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
        preferred_distance = self.radius + target.radius + max(
            15, 31 - self.aggression * 1.7
        )
        forward_amount = 0.0
        if distance > preferred_distance + 8:
            forward_amount = 1.0
        elif distance < preferred_distance - 8:
            forward_amount = -0.45

        attack_distance = self.radius + target.radius + 50 + self.aggression * 2
        strafe_amount = (
            0.72 * self.strafe_direction
            if distance < attack_distance + 45
            else 0.0
        )
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

        dash_interval = max(2, 7 - min(5, self.aggression // 2))
        if (
            self.action_count % dash_interval == 0
            and self.strafe_dash(self.strafe_direction, 52)
        ):
            self.action_cooldown = 0.38 * self.cooldown_factor
            return

        target_is_strafing = (
            target_lateral_speed >= 65 and distance <= attack_distance + 16
        )
        kick_interval = max(2, 5 - min(3, self.aggression // 3))
        if target_is_strafing or self.action_count % kick_interval == 0:
            self.start_kick(side)
            self.action_cooldown = 0.78 * self.cooldown_factor
        else:
            self.start_charging(side)
            self.charging_side = side
            self.charge_goal = 0.5 if self.boss else 0.28

    def draw_silhouette_details(self, surface: pygame.Surface) -> None:
        """Add fins, spikes, and horns behind the shared ball body."""
        outline = (35, 38, 48)
        right = self.forward.rotate(90)

        if self.threat_level >= 2:
            spike_count = min(5, self.threat_level + 1)
            for index in range(spike_count):
                fraction = index / max(1, spike_count - 1)
                direction = self.forward.rotate(-112 + 224 * fraction)
                base = self.pos + direction * self.radius * 0.78
                tangent = direction.rotate(90)
                points = [
                    base - tangent * max(2, self.radius * 0.16),
                    self.pos
                    + direction * (self.radius + 3 + self.threat_level * 1.4),
                    base + tangent * max(2, self.radius * 0.16),
                ]
                pygame.draw.polygon(surface, self.accent_color, points)
                pygame.draw.aalines(surface, outline, True, points)

        has_horns = self.threat_level >= 3 or self.dominant_stat == "aggression"
        if has_horns:
            horn_length = 6 + self.threat_level * 1.5
            for side_sign in (-1, 1):
                horn_direction = (self.forward * 0.75 + right * side_sign).normalize()
                base_direction = self.forward * 0.42 + right * side_sign * 0.63
                base = self.pos + base_direction * self.radius
                points = [
                    base - right * side_sign * 2.5,
                    base + horn_direction * horn_length,
                    base + self.forward * 3,
                ]
                pygame.draw.polygon(surface, (226, 211, 169), points)
                pygame.draw.aalines(surface, outline, True, points)

        if self.dominant_stat in {"speed", "turn"}:
            for side_sign in (-1, 1):
                root = self.pos - self.forward * self.radius * 0.35
                root += right * side_sign * self.radius * 0.72
                if self.dominant_stat == "speed":
                    tip_direction = (
                        -self.forward + right * side_sign * 0.55
                    ).normalize()
                else:
                    tip_direction = right * side_sign
                points = [
                    root - self.forward * 3,
                    root + tip_direction * (5 + self.detail_variant * 1.5),
                    root + self.forward * 3,
                ]
                pygame.draw.polygon(surface, self.limb_color, points)
                pygame.draw.aalines(surface, outline, True, points)

    def draw_body_marking(self, surface: pygame.Surface) -> None:
        """Paint one of several stable name-derived markings on the back."""
        color = self.tint(self.accent_color, 0.62 if not self.alive else 1.0)
        right = self.forward.rotate(90)
        rear = self.pos - self.forward * self.radius * 0.37
        size = max(2, round(self.radius * 0.21))

        if self.marking_style == 0:
            pygame.draw.circle(surface, color, rear, size)
        elif self.marking_style == 1:
            pygame.draw.line(
                surface,
                color,
                rear - right * self.radius * 0.62,
                rear + right * self.radius * 0.62,
                max(2, size),
            )
        elif self.marking_style == 2:
            points = [
                rear - right * size - self.forward * size,
                rear,
                rear + right * size - self.forward * size,
            ]
            pygame.draw.lines(surface, color, False, points, max(2, size // 2))
        elif self.marking_style == 3:
            for side_sign in (-1, 1):
                pygame.draw.circle(
                    surface,
                    color,
                    rear + right * side_sign * size,
                    size // 2 + 1,
                )
        elif self.marking_style == 4:
            points = [
                rear - self.forward * size,
                rear + right * size,
                rear + self.forward * size,
                rear - right * size,
            ]
            pygame.draw.polygon(surface, color, points)
        else:
            pygame.draw.line(
                surface,
                color,
                rear - right * size - self.forward * size,
                rear + right * size + self.forward * size,
                2,
            )
            pygame.draw.line(
                surface,
                color,
                rear - right * size + self.forward * size,
                rear + right * size - self.forward * size,
                2,
            )

    def draw_archetype_detail(self, surface: pygame.Surface) -> None:
        """Expose the strongest stat through a small readable costume detail."""
        outline = (35, 38, 48)
        right = self.forward.rotate(90)
        if self.dominant_stat == "health":
            pygame.draw.circle(surface, self.accent_color, self.pos, self.radius - 3, 2)
        elif self.dominant_stat == "damage":
            for side in self.SIDES:
                hand = self.hand_position(side)
                pygame.draw.circle(
                    surface, self.accent_color, hand, self.hand_radius - 1, 2
                )
        elif self.dominant_stat == "attack_speed":
            band_center = self.pos + self.forward * self.radius * 0.12
            pygame.draw.line(
                surface,
                self.accent_color,
                band_center - right * self.radius * 0.82,
                band_center + right * self.radius * 0.82,
                max(2, self.radius // 5),
            )
        elif self.dominant_stat == "aggression":
            mouth = self.pos + self.forward * self.radius * 0.77
            pygame.draw.line(
                surface,
                outline,
                mouth - right * self.radius * 0.28,
                mouth + right * self.radius * 0.28,
                2,
            )

    def draw_mean_face(self, surface: pygame.Surface) -> None:
        if not self.alive or self.threat_level <= 0:
            return
        outline = (35, 38, 48)
        right = self.forward.rotate(90)
        eye_base = self.pos + self.forward * self.radius * 0.45
        eye_offset = max(4, self.radius * 0.34)
        eye_radius = max(2, round(self.radius * 0.2))
        brow_drop = min(eye_radius + 1, 1 + self.threat_level * 0.45)

        if self.threat_level >= 3:
            eye_color = (255, 206, 104) if self.threat_level < 5 else (255, 112, 74)
            for side_sign in (-1, 1):
                eye = eye_base + right * side_sign * eye_offset
                pygame.draw.circle(surface, eye_color, eye, eye_radius)
                pygame.draw.circle(
                    surface,
                    outline,
                    eye + self.forward * 2,
                    max(1, eye_radius // 2),
                )

        for side_sign in (-1, 1):
            eye = eye_base + right * side_sign * eye_offset
            outer = eye + right * side_sign * eye_radius - self.forward * brow_drop
            inner = eye - right * side_sign * eye_radius + self.forward * brow_drop
            pygame.draw.line(surface, outline, outer, inner, 2 + self.threat_level // 3)

        if self.threat_level >= 2:
            mouth = self.pos + self.forward * self.radius * 0.78
            half_width = self.radius * (0.2 + self.threat_level * 0.025)
            pygame.draw.line(
                surface,
                outline,
                mouth - right * half_width,
                mouth + right * half_width,
                2,
            )
            if self.threat_level >= 3:
                fang_size = max(2, round(self.radius * 0.14))
                for side_sign in (-1, 1):
                    root = mouth + right * side_sign * half_width * 0.58
                    points = [
                        root - right * side_sign * fang_size * 0.55,
                        root + right * side_sign * fang_size * 0.55,
                        root + self.forward * fang_size,
                    ]
                    pygame.draw.polygon(surface, (250, 246, 219), points)
                    pygame.draw.aalines(surface, outline, True, points)

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        self.draw_silhouette_details(surface)
        super().draw(surface, font, show_status=True)
        self.draw_body_marking(surface)
        self.draw_archetype_detail(surface)
        self.draw_mean_face(surface)
