"""Shared movement, combat, and rendering for every brawler entity."""

from __future__ import annotations

import math
from collections.abc import Iterable

import pygame

from .items import Weapon, WeaponSpec


class Entity:
    """A ball-bodied brawler with two hands, two feet, and shared combat rules."""

    SIDES = ("left", "right")
    base_punch_duration = 0.24
    base_kick_duration = 0.42
    base_kick_cooldown = 0.62
    punch_duration = base_punch_duration
    kick_duration = base_kick_duration
    max_charge_time = 0.75
    overcharge_max_time = 2.5
    overcharge_health_ratio = 0.35

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
        attack_speed_multiplier: float = 1.0,
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
        self.power_damage_multiplier = 1.0
        self.movement_speed_multiplier = 1.0
        self.set_attack_speed(attack_speed_multiplier)

        self.angle = 0.0
        self.flash = 0.0
        self.charging = {side: False for side in self.SIDES}
        self.charge = {side: 0.0 for side in self.SIDES}
        self.punch_time = {side: 0.0 for side in self.SIDES}
        self.punch_hits = {side: set() for side in self.SIDES}
        self.weapons: dict[str, Weapon | None] = {
            side: None for side in self.SIDES
        }
        self.weapon_fired = {side: False for side in self.SIDES}
        self.shot_tracer_time = {side: 0.0 for side in self.SIDES}
        self.shot_tracer: dict[
            str, tuple[pygame.Vector2, pygame.Vector2] | None
        ] = {side: None for side in self.SIDES}
        self.kick_time = {side: 0.0 for side in self.SIDES}
        self.kick_cooldown = {side: 0.0 for side in self.SIDES}
        self.kick_hits = {side: set() for side in self.SIDES}
        self.dash_cooldown = 0.0
        self.dash_time = 0.0
        self.dash_direction = 0.0
        self.dash_speed = max(480.0, speed * 2.75)
        self.fast_turn_remaining = 0.0
        self.fast_turn_speed = max(570.0, turn_speed * 3.2)
        self.knockback_velocity = pygame.Vector2()
        self.defeated_time = 0.0
        self.ragdoll_spin = 0.0

    def set_attack_speed(self, multiplier: float) -> None:
        """Scale attack animations and reusable-action cooldowns."""
        self.attack_speed_multiplier = max(0.5, multiplier)
        self.punch_duration = (
            self.base_punch_duration / self.attack_speed_multiplier
        )
        self.kick_duration = self.base_kick_duration / self.attack_speed_multiplier
        self.kick_cooldown_duration = (
            self.base_kick_cooldown / self.attack_speed_multiplier
        )

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

    @property
    def ready_to_despawn(self) -> bool:
        """A defeated ragdoll remains until all visible motion has settled."""
        return (
            not self.alive
            and self.defeated_time >= 0.55
            and self.knockback_velocity.length_squared() <= 12 * 12
            and abs(self.ragdoll_spin) <= 10
        )

    @property
    def can_overcharge(self) -> bool:
        return self.health / self.max_health <= self.overcharge_health_ratio

    @property
    def charge_limit(self) -> float:
        return self.overcharge_max_time if self.can_overcharge else self.max_charge_time

    @property
    def movement_factor(self) -> float:
        """Charging increasingly trades mobility for potential knockback."""
        active_charge = max(
            (self.charge[side] for side in self.SIDES if self.charging[side]),
            default=0.0,
        )
        normal_ratio = self.clamp(active_charge / self.max_charge_time, 0, 1)
        overcharge_ratio = self.clamp(
            (active_charge - self.max_charge_time)
            / (self.overcharge_max_time - self.max_charge_time),
            0,
            1,
        )
        charge_factor = 1.0 - 0.45 * normal_ratio - 0.40 * overcharge_ratio
        if self.knockback_velocity.length_squared() > 300 * 300:
            charge_factor *= 0.25
        return charge_factor

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
        if self.kick_time["left"] > 0 or self.kick_time["right"] > 0:
            return
        movement = pygame.Vector2(strafe_amount, forward_amount)
        if movement.length_squared() > 1:
            movement = movement.normalize()
        forward_speed = self.speed if movement.y >= 0 else self.backwards_speed
        forward_speed *= self.movement_factor
        self.pos += (
            self.forward
            * movement.y
            * forward_speed
            * self.movement_speed_multiplier
            * dt
        )
        self.pos += (
            self.forward.rotate(90)
            * movement.x
            * self.speed
            * self.movement_speed_multiplier
            * self.movement_factor
            * dt
        )
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

    def separate_from(self, other: Entity, apply_impact: bool = True) -> bool:
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

        if apply_impact:
            self.resolve_impact(other, offset)

        correction = offset * ((minimum_distance - distance) / 2 + 0.01)
        self.pos -= correction
        other.pos += correction
        self.keep_in_arena()
        other.keep_in_arena()
        return True

    def resolve_swept_collision(
        self,
        other: Entity,
        self_start: pygame.Vector2,
        other_start: pygame.Vector2,
        *,
        apply_impact: bool = True,
    ) -> bool:
        """Resolve a collision crossed between the start and end of a frame.

        Ordinary overlap checks only see the final positions, so a fast fling can
        move from one side of a body to the other in a single frame. Treat both
        frame movements as line segments and solve for the first time their
        circular bodies touch.
        """
        minimum_distance = self.radius + other.radius
        start_offset = other_start - self_start

        # Existing overlaps are handled by separate_from(), which has a stable
        # fallback normal and can correct the full penetration depth.
        if start_offset.length_squared() <= minimum_distance * minimum_distance:
            return False

        self_movement = self.pos - self_start
        other_movement = other.pos - other_start
        relative_movement = other_movement - self_movement
        movement_squared = relative_movement.length_squared()
        if movement_squared <= 0:
            return False

        linear_term = 2 * start_offset.dot(relative_movement)
        constant_term = (
            start_offset.length_squared() - minimum_distance * minimum_distance
        )
        discriminant = (
            linear_term * linear_term
            - 4 * movement_squared * constant_term
        )
        if discriminant < 0:
            return False

        impact_time = (
            -linear_term - math.sqrt(discriminant)
        ) / (2 * movement_squared)
        if not 0 <= impact_time <= 1:
            return False

        self.pos = self_start + self_movement * impact_time
        other.pos = other_start + other_movement * impact_time
        normal = other.pos - self.pos
        if normal.length_squared() == 0:
            normal = pygame.Vector2(1, 0)
        else:
            normal = normal.normalize()

        if apply_impact:
            self.resolve_impact(other, normal)

        # Leave the bodies just outside contact so floating-point rounding does
        # not make the iterative overlap pass resolve the same pair again.
        contact_slop = normal * 0.005
        self.pos -= contact_slop
        other.pos += contact_slop
        self.keep_in_arena()
        other.keep_in_arena()
        return True

    def resolve_impact(self, other: Entity, normal: pygame.Vector2) -> None:
        """Transfer a strong collision into damage and secondary knockback."""
        closing_speed = (self.knockback_velocity - other.knockback_velocity).dot(normal)
        if closing_speed <= 280:
            return

        damage = min(28.0, (closing_speed - 280) * 0.032)
        self_towards = max(0.0, self.knockback_velocity.dot(normal))
        other_towards = max(0.0, -other.knockback_velocity.dot(normal))

        if self_towards >= other_towards:
            other.take_damage(damage)
            self.take_damage(damage * 0.2)
            other.knockback_velocity += normal * self_towards * 0.62
            self.knockback_velocity -= normal * self_towards * 0.78
        else:
            self.take_damage(damage)
            other.take_damage(damage * 0.2)
            self.knockback_velocity -= normal * other_towards * 0.62
            other.knockback_velocity += normal * other_towards * 0.78

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
        self.weapon_fired[side] = False

    def equip_weapon(
        self,
        spec: WeaponSpec,
        side: str | None = None,
        *,
        durability: int | None = None,
    ) -> str:
        """Equip a fresh weapon, preferring an empty or more worn hand."""
        if side not in self.SIDES:
            empty_side = next(
                (
                    candidate
                    for candidate in self.SIDES
                    if self.weapons[candidate] is None
                ),
                None,
            )
            if empty_side is not None:
                side = empty_side
            else:
                def remaining_durability(candidate: str) -> int:
                    weapon = self.weapons[candidate]
                    assert weapon is not None
                    return weapon.durability

                side = min(self.SIDES, key=remaining_durability)
        assert side is not None
        self.weapons[side] = Weapon.from_spec(spec)
        if durability is not None:
            self.weapons[side].durability = max(1, min(spec.durability, durability))
        return side

    @staticmethod
    def point_segment_distance(
        point: pygame.Vector2,
        start: pygame.Vector2,
        end: pygame.Vector2,
    ) -> float:
        segment = end - start
        if segment.length_squared() == 0:
            return point.distance_to(start)
        progress = Entity.clamp(
            (point - start).dot(segment) / segment.length_squared(), 0, 1
        )
        return point.distance_to(start + segment * progress)

    def weapon_direction(self, side: str) -> pygame.Vector2:
        """Return the current thrust, sweep, or aim direction for a weapon."""
        weapon = self.weapons[side]
        if weapon is None:
            return self.forward
        if weapon.spec.attack_style != "swing" or self.punch_time[side] <= 0:
            return self.forward
        progress = 1 - self.punch_time[side] / self.punch_duration
        side_sign = 1 if side == "left" else -1
        return self.forward.rotate(side_sign * (105 - 210 * progress))

    def weapon_tip(self, side: str, *, attack_range: bool = False) -> pygame.Vector2:
        weapon = self.weapons[side]
        if weapon is None:
            return self.hand_position(side)
        reach = weapon.spec.attack_range if attack_range else weapon.spec.reach
        return self.hand_position(side) + self.weapon_direction(side) * reach

    def start_kick(self, side: str) -> None:
        if (
            self.kick_time["left"] > 0
            or self.kick_time["right"] > 0
            or self.kick_cooldown[side] > 0
        ):
            return
        self.kick_time[side] = self.kick_duration
        self.kick_cooldown[side] = self.kick_cooldown_duration
        self.kick_hits[side].clear()

    def update_state(self, dt: float) -> None:
        """Advance timers shared by human- and AI-controlled entities."""
        if not self.alive:
            self.defeated_time += dt
            spin_step = math.copysign(
                min(abs(self.ragdoll_spin), 180 * dt), self.ragdoll_spin
            )
            self.angle = (self.angle + self.ragdoll_spin * dt) % 360
            self.ragdoll_spin -= spin_step

        for side in self.SIDES:
            if self.charging[side]:
                self.charge[side] = min(
                    self.charge_limit, self.charge[side] + dt
                )

            previous_punch_time = self.punch_time[side]
            self.punch_time[side] = max(0.0, previous_punch_time - dt)
            if self.punch_time[side] <= 0 < previous_punch_time:
                self.charge[side] = 0.0

            self.kick_time[side] = max(0.0, self.kick_time[side] - dt)
            self.kick_cooldown[side] = max(0.0, self.kick_cooldown[side] - dt)
            self.shot_tracer_time[side] = max(
                0.0, self.shot_tracer_time[side] - dt
            )

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
                * self.movement_factor
                * dash_dt
            )
            self.dash_time = max(0.0, self.dash_time - dash_dt)
            self.keep_in_arena()

        self.apply_knockback(dt)

        self.dash_cooldown = max(0.0, self.dash_cooldown - dt)
        self.flash = max(0.0, self.flash - dt)

    def apply_knockback(self, dt: float) -> None:
        """Move from impacts, applying damage when a high-speed fling hits a wall."""
        speed = self.knockback_velocity.length()
        if speed <= 0:
            return

        self.pos += self.knockback_velocity * dt
        left = self.arena.left + self.radius
        right = self.arena.right - self.radius
        top = self.arena.top + self.radius
        bottom = self.arena.bottom - self.radius
        wall_impact_speed = 0.0

        if self.pos.x < left or self.pos.x > right:
            wall_impact_speed = max(wall_impact_speed, abs(self.knockback_velocity.x))
            self.pos.x = self.clamp(self.pos.x, left, right)
            self.knockback_velocity.x *= -0.12
        if self.pos.y < top or self.pos.y > bottom:
            wall_impact_speed = max(wall_impact_speed, abs(self.knockback_velocity.y))
            self.pos.y = self.clamp(self.pos.y, top, bottom)
            self.knockback_velocity.y *= -0.12

        if wall_impact_speed > 360:
            self.take_damage(min(30.0, (wall_impact_speed - 360) * 0.038))

        remaining_speed = self.knockback_velocity.length()
        if remaining_speed > 0:
            new_speed = max(0.0, remaining_speed - 760 * dt)
            self.knockback_velocity.scale_to_length(new_speed)

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
        position = self.pos - self.forward * (self.radius - 8)
        position += side * (self.radius + 1)
        if self.kick_time[side_name] > 0:
            progress = 1 - self.kick_time[side_name] / self.kick_duration
            sweep_sign = 1 if side_name == "left" else -1
            sweep_angle = sweep_sign * (-125 + 180 * progress)
            radial = self.forward.rotate(sweep_angle)
            reach = self.radius + 8 + math.sin(progress * math.pi) * (
                self.radius + 25
            )
            position = self.pos + radial * reach
        return position

    def foot_orientation(self, side_name: str) -> pygame.Vector2:
        if self.kick_time[side_name] <= 0:
            return self.forward
        offset = self.foot_position(side_name) - self.pos
        return offset.normalize() if offset.length_squared() else self.forward

    def kick_knockback_direction(self, side_name: str) -> pygame.Vector2:
        """Blend outward and tangential force in the direction of the sweep."""
        radial = self.foot_orientation(side_name)
        sweep_sign = 1 if side_name == "left" else -1
        tangent = radial.rotate(90 * sweep_sign)
        return (radial * 0.4 + tangent * 0.75).normalize()

    def spend_weapon_use(self, side: str) -> None:
        weapon = self.weapons[side]
        if weapon is None:
            return
        weapon.durability -= 1
        if weapon.durability <= 0:
            self.weapons[side] = None

    def fire_gun(
        self,
        side: str,
        targets: tuple[Entity, ...],
        power_ratio: float,
    ) -> None:
        """Fire one hitscan round at the closest body along the aim line."""
        weapon = self.weapons[side]
        if weapon is None or self.weapon_fired[side]:
            return
        self.weapon_fired[side] = True
        muzzle = self.weapon_tip(side)
        ray_end = self.weapon_tip(side, attack_range=True)
        candidates = [
            target
            for target in targets
            if self.point_segment_distance(target.pos, muzzle, ray_end)
            <= target.radius + weapon.spec.width
            and (target.pos - muzzle).dot(self.forward) >= 0
        ]
        hit_target = min(
            candidates,
            key=lambda target: muzzle.distance_squared_to(target.pos),
            default=None,
        )
        tracer_end = ray_end
        if hit_target is not None:
            tracer_end = hit_target.pos.copy()
            damage = (
                (9 + 18 * power_ratio)
                * self.damage_scale
                * self.power_damage_multiplier
                * weapon.spec.damage_multiplier
            )
            knockback = (
                (110 + 170 * power_ratio)
                * self.damage_scale
                * weapon.spec.knockback_multiplier
            )
            hit_target.take_damage(damage, self.forward * knockback)
            self.punch_hits[side].add(id(hit_target))
        self.shot_tracer[side] = (muzzle.copy(), tracer_end)
        self.shot_tracer_time[side] = 0.09
        self.spend_weapon_use(side)

    def attack(self, targets: Iterable[Entity]) -> None:
        """Resolve active hand and foot attacks against other entities."""
        targets = tuple(target for target in targets if target is not self and target.alive)
        for side in self.SIDES:
            if self.punch_time[side] > 0:
                hand = self.hand_position(side)
                weapon = self.weapons[side]
                power_ratio = self.clamp(
                    self.charge[side] / self.max_charge_time, 0, 1
                )
                overcharge_ratio = self.clamp(
                    (self.charge[side] - self.max_charge_time)
                    / (self.overcharge_max_time - self.max_charge_time),
                    0,
                    1,
                )
                if weapon is not None and weapon.spec.attack_style == "shoot":
                    self.fire_gun(side, targets, power_ratio)
                else:
                    for target in targets:
                        target_id = id(target)
                        if target_id in self.punch_hits[side]:
                            continue
                        if weapon is None:
                            hit = (
                                hand.distance_to(target.pos)
                                <= self.hand_radius + target.radius
                            )
                        else:
                            hit = self.point_segment_distance(
                                target.pos,
                                hand,
                                self.weapon_tip(side, attack_range=True),
                            ) <= weapon.spec.width + target.radius
                        if hit:
                            weapon_damage = (
                                weapon.spec.damage_multiplier
                                if weapon is not None
                                else 1.0
                            )
                            weapon_knockback = (
                                weapon.spec.knockback_multiplier
                                if weapon is not None
                                else 1.0
                            )
                            damage = (
                                (10 + 22 * power_ratio)
                                * self.damage_scale
                                * self.power_damage_multiplier
                                * weapon_damage
                            )
                            knockback = (
                                170
                                + 270 * power_ratio
                                + 700 * overcharge_ratio**1.4
                            ) * self.damage_scale * weapon_knockback
                            attack_direction = (
                                self.weapon_direction(side)
                                if weapon is not None
                                else self.forward
                            )
                            target.take_damage(
                                damage, attack_direction * knockback
                            )
                            self.punch_hits[side].add(target_id)
                            if weapon is not None:
                                self.spend_weapon_use(side)
                                if self.weapons[side] is None:
                                    break

            if self.kick_time[side] > 0:
                foot = self.foot_position(side)
                for target in targets:
                    target_id = id(target)
                    if target_id in self.kick_hits[side]:
                        continue
                    if foot.distance_to(target.pos) <= self.radius + 1 + target.radius:
                        target.take_damage(
                            13 * self.damage_scale * self.power_damage_multiplier,
                            self.kick_knockback_direction(side)
                            * 420
                            * self.damage_scale,
                        )
                        self.kick_hits[side].add(target_id)

    def take_damage(self, amount: float, knockback: pygame.Vector2 | None = None) -> None:
        was_alive = self.alive
        self.health = max(0.0, self.health - amount)
        self.flash = 0.11
        if knockback is not None:
            self.knockback_velocity += knockback
        if was_alive and not self.alive:
            self.begin_ragdoll(knockback)

    def begin_ragdoll(self, knockback: pygame.Vector2 | None) -> None:
        """Cancel combat actions and start a visible defeated tumble."""
        for side in self.SIDES:
            self.charging[side] = False
            self.charge[side] = 0.0
            self.punch_time[side] = 0.0
            self.kick_time[side] = 0.0
        horizontal_direction = 1
        if knockback is not None and knockback.x < 0:
            horizontal_direction = -1
        self.ragdoll_spin = 220.0 * horizontal_direction
        self.defeated_time = 0.0

    def fist_color(self, side: str) -> tuple[int, int, int]:
        ratio = self.clamp(self.charge[side] / self.max_charge_time, 0, 1)
        overcharge_ratio = self.clamp(
            (self.charge[side] - self.max_charge_time)
            / (self.overcharge_max_time - self.max_charge_time),
            0,
            1,
        )
        charged_color = (255, 231, 125)
        normal_color = tuple(
            round(charged * ratio + normal * (1 - ratio))
            for normal, charged in zip(self.limb_color, charged_color)
        )
        overcharge_color = (255, 78, 164)
        return tuple(
            round(overcharged * overcharge_ratio + normal * (1 - overcharge_ratio))
            for normal, overcharged in zip(normal_color, overcharge_color)
        )

    def draw_weapon(self, surface: pygame.Surface, side: str) -> None:
        weapon = self.weapons[side]
        if weapon is None:
            return
        outline = (35, 38, 48)
        spec = weapon.spec
        hand = self.hand_position(side)
        tip = self.weapon_tip(side)
        right = self.forward.rotate(90)
        pygame.draw.line(surface, outline, hand, tip, spec.width + 4)
        pygame.draw.line(surface, spec.color, hand, tip, spec.width)
        if spec.name == "SWORD":
            guard = hand + self.forward * 3
            pygame.draw.line(
                surface, outline, guard - right * 7, guard + right * 7, 5
            )
            pygame.draw.line(
                surface, spec.accent, guard - right * 6, guard + right * 6, 3
            )
            pygame.draw.polygon(
                surface,
                spec.color,
                [tip + self.forward * 6, tip - right * 3, tip + right * 3],
            )
        elif spec.name == "GUN":
            direction = self.weapon_direction(side)
            grip_root = hand + direction * 7
            grip_tip = grip_root - direction * 3 + right * (
                7 if side == "right" else -7
            )
            pygame.draw.line(surface, outline, grip_root, grip_tip, 7)
            pygame.draw.line(surface, spec.accent, grip_root, grip_tip, 4)
        else:
            pygame.draw.circle(surface, outline, tip, spec.width + 2)
            pygame.draw.circle(surface, spec.accent, tip, spec.width)

    def draw_shot_tracers(self, surface: pygame.Surface) -> None:
        for side in self.SIDES:
            tracer = self.shot_tracer[side]
            if self.shot_tracer_time[side] <= 0 or tracer is None:
                continue
            start, end = tracer
            pygame.draw.line(surface, (255, 244, 170), start, end, 3)
            pygame.draw.circle(surface, (255, 187, 73), start, 5)

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

        self.draw_shot_tracers(surface)

        for side in self.SIDES:
            self.draw_oriented_oval(
                surface,
                self.foot_position(side),
                self.foot_orientation(side),
                self.radius * 1.8,
                self.radius * 1.05,
                self.limb_color,
                outline,
            )

        pygame.draw.circle(surface, outline, self.pos, self.radius + 3)
        body_color = self.body_color
        if not self.alive:
            body_color = tuple(round(channel * 0.62) for channel in body_color)
        pygame.draw.circle(
            surface, hit_color if self.flash else body_color, self.pos, self.radius
        )

        eye_base = self.pos + self.forward * self.radius * 0.45
        eye_offset = max(4, self.radius * 0.34)
        eye_radius = max(2, round(self.radius * 0.2))
        for eye_side in (-1, 1):
            eye = eye_base + right * eye_side * eye_offset
            if self.alive:
                pygame.draw.circle(surface, (250, 250, 245), eye, eye_radius)
                pygame.draw.circle(
                    surface, outline, eye + self.forward * 2, max(1, eye_radius // 2)
                )
            else:
                cross = max(2, eye_radius)
                pygame.draw.line(
                    surface,
                    outline,
                    eye - pygame.Vector2(cross, cross),
                    eye + pygame.Vector2(cross, cross),
                    2,
                )
                pygame.draw.line(
                    surface,
                    outline,
                    eye + pygame.Vector2(-cross, cross),
                    eye + pygame.Vector2(cross, -cross),
                    2,
                )

        for side in self.SIDES:
            hand = self.hand_position(side)
            pygame.draw.circle(surface, outline, hand, self.hand_radius + 2)
            pygame.draw.circle(surface, self.fist_color(side), hand, self.hand_radius)
            self.draw_weapon(surface, side)

        if show_status and font is not None and self.alive:
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
