"""A tiny, self-contained Kilin Kolin pygame prototype."""

from __future__ import annotations

import os
import random

import pygame

from entities import Enemy, Entity, Player


WIDTH, HEIGHT = 960, 640
ARENA = pygame.Rect(34, 70, WIDTH - 68, HEIGHT - 104)
FPS = 60

INK = (35, 38, 48)
PAPER = (239, 232, 210)
ARENA_COLOR = (197, 210, 176)

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
        self.player = Player(ARENA)
        self.stage = 0
        self.state = "playing"
        self.notice = "Defeat the stranger"
        self.notice_time = 2.2
        self.enemies = [
            Enemy(pygame.Vector2(WIDTH / 2, 180), "Stranger", ARENA, speed=58)
        ]

    def spawn_connected_people(self) -> None:
        self.enemies = [
            Enemy(pygame.Vector2(210, 160), "Connected A", ARENA, speed=64),
            Enemy(pygame.Vector2(750, 190), "Connected B", ARENA, speed=72),
        ]
        self.notice = "Connected people appeared!"
        self.notice_time = 2.2

    def spawn_final_boss(self) -> None:
        self.enemies = [
            Enemy(
                pygame.Vector2(WIDTH / 2, 165),
                "HITLER",
                ARENA,
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
                self.player.handle_keydown(event.key, self.enemies)
        elif event.type == pygame.KEYUP and self.state == "playing":
            self.player.handle_keyup(event.key)
        return True

    def resolve_entity_collisions(self) -> None:
        """Keep every living entity's circular body from overlapping another."""
        entities: list[Entity] = [self.player, *self.enemies]
        for _ in range(12):
            corrected_overlap = False
            for index, entity in enumerate(entities):
                for other in entities[index + 1 :]:
                    corrected_overlap = entity.separate_from(other) or corrected_overlap
            if not corrected_overlap:
                break

    def update(self, dt: float) -> None:
        if self.state != "playing":
            return

        self.player.update(dt, pygame.key.get_pressed(), self.enemies)
        for enemy in self.enemies:
            enemy.update(dt, self.player)
        self.resolve_entity_collisions()

        self.player.attack(self.enemies)
        self.enemies = [enemy for enemy in self.enemies if enemy.alive]
        for enemy in self.enemies:
            enemy.attack((self.player,))
        self.resolve_entity_collisions()

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
        inner.width = round(inner.width * Entity.clamp(ratio, 0, 1))
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
        self.player.draw_target_indicator(self.screen)

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
            "W/S move   Shift lock   A/D turn/strafe   Q/E turn/dash   J/K punch   U/I kick",
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
