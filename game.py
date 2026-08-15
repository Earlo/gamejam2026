"""A tiny, self-contained Kilin Kolin pygame prototype."""

from __future__ import annotations

import math
import os
import random
from dataclasses import dataclass

import pygame


WIDTH, HEIGHT = 960, 640
ARENA = pygame.Rect(34, 70, WIDTH - 68, HEIGHT - 104)
FPS = 60

INK = (35, 38, 48)
PAPER = (239, 232, 210)
ARENA_COLOR = (197, 210, 176)
PLAYER_COLOR = (71, 139, 204)
PLAYER_LIGHT = (127, 190, 235)
ENEMY_COLOR = (202, 82, 75)
HIT_COLOR = (255, 231, 125)

def fist_color(power_ratio: float) -> tuple[int, int, int]:
    """Return a color for a fist based on its charge power."""
    red = round(255 * power_ratio + 71 * (1 - power_ratio))
    green = round(231 * power_ratio + 139 * (1 - power_ratio))
    blue = round(125 * power_ratio + 204 * (1 - power_ratio))
    return (red, green, blue)

def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def facing(angle: float) -> pygame.Vector2:
    """Return a screen-space direction where zero degrees points upward."""
    return pygame.Vector2(0, -1).rotate(angle)


def draw_oriented_oval(
    surface: pygame.Surface,
    center: pygame.Vector2,
    along: pygame.Vector2,
    length: float,
    width: float,
    color: tuple[int, int, int],
) -> None:
    """Draw an ellipse from points so it can face in any direction."""
    side = along.rotate(90)
    points = []
    for index in range(18):
        radians = math.tau * index / 18
        point = center + along * math.cos(radians) * length / 2
        point += side * math.sin(radians) * width / 2
        points.append(point)
    pygame.draw.polygon(surface, color, points)
    pygame.draw.aalines(surface, INK, True, points)


@dataclass
class Enemy:
    pos: pygame.Vector2
    name: str
    radius: int = 12
    max_health: float = 38
    speed: float = 68
    boss: bool = False

    def __post_init__(self) -> None:
        self.health = self.max_health
        self.flash = 0.0

    def update(self, dt: float, player_pos: pygame.Vector2) -> None:
        offset = player_pos - self.pos
        if offset.length_squared() > 1:
            self.pos += offset.normalize() * self.speed * dt
        self.pos.x = clamp(self.pos.x, ARENA.left + self.radius, ARENA.right - self.radius)
        self.pos.y = clamp(self.pos.y, ARENA.top + self.radius, ARENA.bottom - self.radius)
        self.flash = max(0.0, self.flash - dt)

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        color = HIT_COLOR if self.flash else ((137, 45, 50) if self.boss else ENEMY_COLOR)
        pygame.draw.circle(surface, INK, self.pos, self.radius + 3)
        pygame.draw.circle(surface, color, self.pos, self.radius)

        # A tiny face makes the target direction immediately readable.
        eye_y = self.pos.y - 4
        pygame.draw.circle(surface, INK, (self.pos.x - 7, eye_y), 2)
        pygame.draw.circle(surface, INK, (self.pos.x + 7, eye_y), 2)
        pygame.draw.line(
            surface,
            INK,
            (self.pos.x - 7, self.pos.y + 8),
            (self.pos.x + 7, self.pos.y + 8),
            2,
        )

        bar = pygame.Rect(0, 0, self.radius * 2, 6)
        bar.midbottom = (round(self.pos.x), round(self.pos.y - self.radius - 8))
        pygame.draw.rect(surface, INK, bar, border_radius=3)
        fill = bar.inflate(-2, -2)
        fill.width = round(fill.width * max(0, self.health) / self.max_health)
        pygame.draw.rect(surface, (102, 196, 114), fill, border_radius=2)

        label = font.render(self.name, True, INK)
        surface.blit(label, label.get_rect(midtop=(self.pos.x, self.pos.y + self.radius + 7)))


class Player:
    radius = 12
    hand_radius = 5
    punch_duration = 0.24
    kick_duration = 0.28
    max_charge_time = 0.75

    def __init__(self) -> None:
        self.pos = pygame.Vector2(WIDTH / 2, HEIGHT - 150)
        self.angle = 0.0
        self.health = 100.0
        self.invulnerable = 0.0
        self.flash = 0.0

        self.charging = {"left": False, "right": False}
        self.charge = {"left": 0.0, "right": 0.0}
        self.punch_time = {"left": 0.0, "right": 0.0}
        self.punch_hits = {"left": set(), "right": set()}
        self.kick_time = {"left": 0.0, "right": 0.0}
        self.kick_cooldown = {"left": 0.0, "right": 0.0}
        self.kick_hits = {"left": set(), "right": set()}

    def handle_keydown(self, key: int) -> None:
        if key == pygame.K_q:
            self.angle -= 90
        elif key == pygame.K_e:
            self.angle += 90
        elif key == pygame.K_j and self.punch_time["left"] <= 0:
            self.charging["left"] = True
        elif key == pygame.K_k and self.punch_time["right"] <= 0:
            self.charging["right"] = True
        elif key == pygame.K_u:
            self.start_kick("left")
        elif key == pygame.K_i:
            self.start_kick("right")
        self.angle %= 360

    def handle_keyup(self, key: int) -> None:
        if key == pygame.K_j:
            self.release_punch("left")
        elif key == pygame.K_k:
            self.release_punch("right")

    def release_punch(self, side: str) -> None:
        if not self.charging[side]:
            return
        self.charging[side] = False
        # self.charge[side] = 0.0
        self.punch_time[side] = self.punch_duration
        self.punch_hits[side].clear()

    def start_kick(self, side: str) -> None:
        if self.kick_cooldown[side] > 0:
            return
        self.kick_time[side] = self.kick_duration
        self.kick_cooldown[side] = 0.48
        self.kick_hits[side].clear()

    def update(self, dt: float, keys: pygame.key.ScancodeWrapper) -> None:
        turn = float(keys[pygame.K_d]) - float(keys[pygame.K_a])
        self.angle = (self.angle + turn * 190 * dt) % 360

        direction = facing(self.angle)
        motion = float(keys[pygame.K_w]) - float(keys[pygame.K_s])
        speed = 215 if motion >= 0 else 135
        self.pos += direction * motion * speed * dt
        self.pos.x = clamp(self.pos.x, ARENA.left + self.radius, ARENA.right - self.radius)
        self.pos.y = clamp(self.pos.y, ARENA.top + self.radius, ARENA.bottom - self.radius)

        for side in ("left", "right"):
            if self.charging[side]:
                self.charge[side] = min(
                    self.max_charge_time, self.charge[side] + dt
                )
            new_punch_time = max(0.0, self.punch_time[side] - dt)
            if (new_punch_time <= 0) and (self.punch_time[side] > 0):
                self.charge[side] = 0.0
            self.punch_time[side] = new_punch_time
            self.kick_time[side] = max(0.0, self.kick_time[side] - dt)
            self.kick_cooldown[side] = max(0.0, self.kick_cooldown[side] - dt)

        self.invulnerable = max(0.0, self.invulnerable - dt)
        self.flash = max(0.0, self.flash - dt)

    def hand_position(self, side_name: str) -> pygame.Vector2:
        forward = facing(self.angle)
        right = forward.rotate(90)
        side = -right if side_name == "left" else right
        position = self.pos + side * (self.radius + self.hand_radius)

        if self.charging[side_name]:
            position -= forward * (5 + 10 * self.charge[side_name] / self.max_charge_time)
        elif self.punch_time[side_name] > 0:
            punch_target = self.pos + forward * (28 + 40 * self.charge[side_name] / self.max_charge_time) + side * (self.hand_radius)
            progress = 1 - self.punch_time[side_name] / self.punch_duration
            extension = math.sin(progress * math.pi)
            power = self.charge[side_name] / self.max_charge_time
            position += (punch_target - position) * extension
        return position

    def foot_position(self, side_name: str) -> pygame.Vector2:
        forward = facing(self.angle)
        right = forward.rotate(90)
        side = -right if side_name == "left" else right
        position = self.pos - forward * 20 + side * 13
        if self.kick_time[side_name] > 0:
            progress = 1 - self.kick_time[side_name] / self.kick_duration
            position += forward * math.sin(progress * math.pi) * 63
        return position

    def attack_enemies(self, enemies: list[Enemy]) -> None:
        for side in ("left", "right"):
            if self.punch_time[side] > 0:
                hand = self.hand_position(side)
                power_ratio = self.charge[side] / self.max_charge_time
                for enemy in enemies:
                    enemy_id = id(enemy)
                    if enemy_id in self.punch_hits[side]:
                        continue
                    if hand.distance_to(enemy.pos) <= self.hand_radius + enemy.radius:
                        enemy.health -= 10 + 22 * power_ratio
                        enemy.flash = 0.11
                        enemy.pos += facing(self.angle) * (10 + 25 * power_ratio)
                        self.punch_hits[side].add(enemy_id)

            if self.kick_time[side] > 0:
                foot = self.foot_position(side)
                for enemy in enemies:
                    enemy_id = id(enemy)
                    if enemy_id in self.kick_hits[side]:
                        continue
                    if foot.distance_to(enemy.pos) <= 13 + enemy.radius:
                        enemy.health -= 16
                        enemy.flash = 0.11
                        enemy.pos += facing(self.angle) * 30
                        self.kick_hits[side].add(enemy_id)

    def take_contact_damage(self, amount: float) -> None:
        if self.invulnerable > 0:
            return
        self.health -= amount
        self.invulnerable = 0.65
        self.flash = 0.14

    def draw(self, surface: pygame.Surface) -> None:
        forward = facing(self.angle)
        right = forward.rotate(90)

        # Feet go down first, keeping the small ovals visibly underneath the body.
        for side in ("left", "right"):
            draw_oriented_oval(
                surface,
                self.foot_position(side),
                forward,
                22,
                13,
                PLAYER_LIGHT,
            )

        body_color = HIT_COLOR if self.flash else PLAYER_COLOR
        pygame.draw.circle(surface, INK, self.pos, self.radius + 3)
        pygame.draw.circle(surface, body_color, self.pos, self.radius)

        # Eyes face forward and make turning easy to read.
        eye_base = self.pos + forward * 11
        for eye_side in (-1, 1):
            eye = eye_base + right * eye_side * 8
            pygame.draw.circle(surface, (250, 250, 245), eye, 5)
            pygame.draw.circle(surface, INK, eye + forward * 2, 2)

        for side in ("left", "right"):
            hand = self.hand_position(side)
            pygame.draw.circle(surface, INK, hand, self.hand_radius + 2)
            pygame.draw.circle(surface, fist_color(self.charge[side]), hand, self.hand_radius)


class Game:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Kilin Kolin — Ball Brawler")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 24)
        self.small_font = pygame.font.Font(None, 19)
        self.big_font = pygame.font.Font(None, 64)
        self.reset()

    def reset(self) -> None:
        self.player = Player()
        self.stage = 0
        self.state = "playing"
        self.notice = "Defeat the stranger"
        self.notice_time = 2.2
        self.enemies = [
            Enemy(pygame.Vector2(WIDTH / 2, 180), "Stranger", speed=58)
        ]

    def spawn_connected_people(self) -> None:
        self.enemies = [
            Enemy(pygame.Vector2(210, 160), "Connected A", speed=64),
            Enemy(pygame.Vector2(750, 190), "Connected B", speed=72),
        ]
        self.notice = "Connected people appeared!"
        self.notice_time = 2.2

    def spawn_final_boss(self) -> None:
        self.enemies = [
            Enemy(
                pygame.Vector2(WIDTH / 2, 165),
                "HITLER",
                radius=34,
                max_health=130,
                speed=78,
                boss=True,
            )
        ]
        self.notice = "Final target: HITLER"
        self.notice_time = 2.6

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return False
            if self.state != "playing" and event.key == pygame.K_r:
                self.reset()
            elif self.state == "playing":
                self.player.handle_keydown(event.key)
        elif event.type == pygame.KEYUP and self.state == "playing":
            self.player.handle_keyup(event.key)
        return True

    def update(self, dt: float) -> None:
        if self.state != "playing":
            return

        self.player.update(dt, pygame.key.get_pressed())
        for enemy in self.enemies:
            enemy.update(dt, self.player.pos)
            if enemy.pos.distance_to(self.player.pos) < enemy.radius + self.player.radius:
                self.player.take_contact_damage(8 if not enemy.boss else 13)
                away = self.player.pos - enemy.pos
                if away.length_squared() > 0:
                    self.player.pos += away.normalize() * 7

        self.player.attack_enemies(self.enemies)
        self.enemies = [enemy for enemy in self.enemies if enemy.health > 0]

        if not self.enemies:
            if self.stage == 0:
                self.stage = 1
                self.spawn_connected_people()
            elif self.stage == 1:
                self.stage = 2
                self.spawn_final_boss()
            else:
                self.state = "won"

        if self.player.health <= 0:
            self.player.health = 0
            self.state = "lost"

        self.notice_time = max(0.0, self.notice_time - dt)

    def draw_bar(
        self,
        rect: pygame.Rect,
        ratio: float,
        fill_color: tuple[int, int, int],
        label: str,
    ) -> None:
        pygame.draw.rect(self.screen, INK, rect, border_radius=5)
        inner = rect.inflate(-4, -4)
        pygame.draw.rect(self.screen, (88, 91, 96), inner, border_radius=3)
        inner.width = round(inner.width * clamp(ratio, 0, 1))
        pygame.draw.rect(self.screen, fill_color, inner, border_radius=3)
        text = self.small_font.render(label, True, PAPER)
        self.screen.blit(text, text.get_rect(center=rect.center))

    def draw(self) -> None:
        self.screen.fill(PAPER)
        pygame.draw.rect(self.screen, INK, ARENA.inflate(8, 8), border_radius=18)
        pygame.draw.rect(self.screen, ARENA_COLOR, ARENA, border_radius=14)

        # A little arena texture, deterministic so it does not shimmer.
        rng = random.Random(7)
        for _ in range(70):
            point = (rng.randrange(ARENA.left, ARENA.right), rng.randrange(ARENA.top, ARENA.bottom))
            pygame.draw.circle(self.screen, (183, 198, 161), point, 2)

        for enemy in self.enemies:
            enemy.draw(self.screen, self.small_font)
        self.player.draw(self.screen)

        title = self.font.render("KILIN KOLIN", True, INK)
        self.screen.blit(title, (34, 22))
        objective = self.small_font.render(
            "Goal: follow the connections and defeat Hitler", True, INK
        )
        self.screen.blit(objective, (175, 27))

        self.draw_bar(
            pygame.Rect(WIDTH - 254, 20, 220, 24),
            self.player.health / 100,
            (90, 184, 104),
            f"HEALTH  {round(self.player.health)}",
        )
        self.draw_bar(
            pygame.Rect(42, HEIGHT - 27, 154, 18),
            self.player.charge["left"] / self.player.max_charge_time,
            (102, 171, 224),
            "J  LEFT PUNCH",
        )
        self.draw_bar(
            pygame.Rect(204, HEIGHT - 27, 154, 18),
            self.player.charge["right"] / self.player.max_charge_time,
            (102, 171, 224),
            "K  RIGHT PUNCH",
        )
        controls = self.small_font.render(
            "W/S move   A/D turn   Q/E snap turn   hold J/K punch   U/I kick   Esc quit",
            True,
            INK,
        )
        self.screen.blit(controls, controls.get_rect(bottomright=(WIDTH - 40, HEIGHT - 9)))

        if self.notice_time > 0 and self.state == "playing":
            message = self.font.render(self.notice, True, INK)
            box = message.get_rect(center=(WIDTH / 2, 100)).inflate(24, 14)
            pygame.draw.rect(self.screen, PAPER, box, border_radius=8)
            pygame.draw.rect(self.screen, INK, box, 2, border_radius=8)
            self.screen.blit(message, message.get_rect(center=box.center))

        if self.state != "playing":
            veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            veil.fill((25, 28, 36, 170))
            self.screen.blit(veil, (0, 0))
            headline = "YOU WIN!" if self.state == "won" else "KNOCKED OUT"
            text = self.big_font.render(headline, True, PAPER)
            self.screen.blit(text, text.get_rect(center=(WIDTH / 2, HEIGHT / 2 - 25)))
            restart = self.font.render("Press R to play again", True, PAPER)
            self.screen.blit(restart, restart.get_rect(center=(WIDTH / 2, HEIGHT / 2 + 35)))

        pygame.display.flip()

    def run(self) -> None:
        running = True
        smoke_frames = int(os.environ.get("KILIN_KOLIN_SMOKE_FRAMES", "0"))
        frames = 0
        while running:
            dt = min(self.clock.tick(FPS) / 1000, 0.05)
            for event in pygame.event.get():
                running = self.handle_event(event) and running
            self.update(dt)
            self.draw()
            frames += 1
            if smoke_frames and frames >= smoke_frames:
                running = False
        pygame.quit()


if __name__ == "__main__":
    Game().run()
