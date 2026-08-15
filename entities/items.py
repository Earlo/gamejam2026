"""Collectible weapons and temporary powerups for the arena."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from .player import Player


INK = (35, 38, 48)


@dataclass(frozen=True)
class WeaponSpec:
    """The immutable combat and drawing values shared by a weapon type."""

    name: str
    attack_style: str
    color: tuple[int, int, int]
    accent: tuple[int, int, int]
    reach: int
    attack_range: int
    width: int
    damage_multiplier: float
    knockback_multiplier: float
    durability: int


@dataclass
class Weapon:
    """A weapon equipped in one hand, with durability spent on landed hits."""

    spec: WeaponSpec
    durability: int

    @classmethod
    def from_spec(cls, spec: WeaponSpec) -> Weapon:
        return cls(spec, spec.durability)

    @property
    def name(self) -> str:
        return self.spec.name


WEAPON_SPECS = {
    "club": WeaponSpec(
        "CLUB", "swing", (139, 91, 55), (205, 151, 85), 29, 29, 7, 1.35, 1.55, 10
    ),
    "sword": WeaponSpec(
        "SWORD", "stab", (190, 204, 211), (94, 135, 165), 34, 34, 4, 1.65, 1.18, 8
    ),
    "gun": WeaponSpec(
        "GUN", "shoot", (72, 79, 91), (221, 156, 62), 21, 300, 4, 1.15, 0.62, 12
    ),
}

POWERUP_INFO = {
    "health": ("HEALTH +35", (91, 190, 104)),
    "fury": ("FURY 10s", (220, 73, 79)),
    "haste": ("HASTE 10s", (65, 171, 211)),
}


class DroppedItem:
    """An arena pickup that bobs, expires, and applies itself on contact."""

    lifetime = 22.0
    pickup_radius = 17

    def __init__(
        self,
        pos: pygame.Vector2 | tuple[float, float],
        *,
        powerup: str | None = None,
        weapon_spec: WeaponSpec | None = None,
        weapon_durability: int | None = None,
    ) -> None:
        if (powerup is None) == (weapon_spec is None):
            raise ValueError("a dropped item must contain one powerup or weapon")
        if powerup is not None and powerup not in POWERUP_INFO:
            raise ValueError(f"unknown powerup: {powerup}")
        self.pos = pygame.Vector2(pos)
        self.powerup = powerup
        self.weapon_spec = weapon_spec
        self.weapon_durability = weapon_durability
        self.age = 0.0
        self.collected = False
        self.bob_phase = (self.pos.x * 0.07 + self.pos.y * 0.11) % math.tau

    @property
    def expired(self) -> bool:
        return self.collected or self.age >= self.lifetime

    @property
    def label(self) -> str:
        if self.weapon_spec is not None:
            return self.weapon_spec.name
        assert self.powerup is not None
        return POWERUP_INFO[self.powerup][0]

    def update(self, dt: float) -> None:
        self.age += dt

    def can_collect(self, player: Player) -> bool:
        return self.pos.distance_to(player.pos) <= self.pickup_radius + player.radius

    def collect(self, player: Player) -> str:
        """Apply the pickup and return a short message for the game HUD."""
        if self.collected:
            return ""
        self.collected = True
        if self.weapon_spec is not None:
            side = player.equip_weapon(
                self.weapon_spec, durability=self.weapon_durability
            )
            return f"Picked up {self.weapon_spec.name} ({side} hand)"
        assert self.powerup is not None
        player.apply_powerup(self.powerup)
        return f"Picked up {POWERUP_INFO[self.powerup][0]}"

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        # Blink for the final four seconds so an expiring drop is unambiguous.
        if self.lifetime - self.age < 4 and int(self.age * 8) % 2:
            return
        bob = math.sin(self.age * 4 + self.bob_phase) * 3
        center = self.pos + pygame.Vector2(0, bob)
        shadow = pygame.Rect(0, 0, 28, 8)
        shadow.center = (round(self.pos.x), round(self.pos.y + 13))
        pygame.draw.ellipse(surface, (139, 148, 123), shadow)
        pygame.draw.circle(surface, (245, 238, 210), center, 15)
        pygame.draw.circle(surface, INK, center, 15, 2)

        if self.weapon_spec is not None:
            draw_weapon_icon(surface, center, self.weapon_spec)
        else:
            assert self.powerup is not None
            color = POWERUP_INFO[self.powerup][1]
            if self.powerup == "health":
                pygame.draw.circle(surface, color, center, 8)
                pygame.draw.rect(
                    surface,
                    (250, 245, 225),
                    (center.x - 2, center.y - 6, 4, 12),
                )
                pygame.draw.rect(
                    surface,
                    (250, 245, 225),
                    (center.x - 6, center.y - 2, 12, 4),
                )
            elif self.powerup == "fury":
                points = [
                    center + pygame.Vector2(-2, -10),
                    center + pygame.Vector2(8, -3),
                    center + pygame.Vector2(2, 0),
                    center + pygame.Vector2(5, 9),
                    center + pygame.Vector2(-8, 2),
                ]
                pygame.draw.polygon(surface, color, points)
            else:
                pygame.draw.arc(
                    surface,
                    color,
                    pygame.Rect(center.x - 9, center.y - 9, 18, 18),
                    -1.2,
                    1.2,
                    4,
                )
                pygame.draw.arc(
                    surface,
                    color,
                    pygame.Rect(center.x - 5, center.y - 6, 13, 13),
                    1.9,
                    4.4,
                    3,
                )

        label = font.render(self.label, True, INK)
        surface.blit(label, label.get_rect(midtop=(center.x, center.y + 18)))


def draw_weapon_icon(
    surface: pygame.Surface,
    center: pygame.Vector2,
    spec: WeaponSpec,
) -> None:
    """Draw a compact diagonal representation of a weapon pickup."""
    along = pygame.Vector2(0.7, -0.7)
    start = center - along * 9
    end = center + along * 9
    pygame.draw.line(surface, INK, start, end, max(4, spec.width))
    pygame.draw.line(surface, spec.color, start, end, max(2, spec.width - 3))
    if spec.name == "GUN":
        across = along.rotate(90)
        pygame.draw.line(surface, INK, start, end + along * 2, 8)
        pygame.draw.line(surface, spec.color, start, end + along * 2, 5)
        grip = center - along * 2 + across * 5
        pygame.draw.line(surface, INK, center - along * 2, grip, 6)
        pygame.draw.line(surface, spec.accent, center - along * 2, grip, 3)
    elif spec.name == "SWORD":
        across = along.rotate(90)
        pygame.draw.line(
            surface, spec.accent, start - across * 5, start + across * 5, 3
        )
        pygame.draw.polygon(
            surface,
            spec.color,
            [end + along * 4, end - across * 2, end + across * 2],
        )
    else:
        pygame.draw.circle(surface, spec.accent, end, 4)
