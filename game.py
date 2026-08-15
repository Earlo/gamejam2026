"""A tiny, self-contained Kilin Kolin pygame prototype."""

from __future__ import annotations

import asyncio
import os
import random

import pygame

from entities import Enemy, Entity, Player
from wikigraph import wiki as wiki_api


PLAYFIELD_WIDTH = 960
WIDTH, HEIGHT = 1280, 700
ARENA = pygame.Rect(34, 70, PLAYFIELD_WIDTH - 68, HEIGHT - 104)
FPS = 60
MAX_ACTIVE_ENEMIES = 4
SPAWN_INTERVAL = 1.6

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
        self.wiki_loop = asyncio.new_event_loop()
        self.reset()

    def reset(self) -> None:
        for task in getattr(self, "wiki_tasks", {}):
            task.cancel()
        self.wiki_tasks: dict[
            asyncio.Task[object], tuple[str, str | None, int]
        ] = {}
        self.player = Player(ARENA)
        progress = wiki_api.load_progress()
        self.people_graph = progress["people"]
        self.tree_roots = progress["roots"]
        self.defeated_people = set(progress["defeated"])
        self.possible_enemies = set(progress["pending"]) - self.defeated_people
        self.active_people: set[str] = set()
        self.enemies: list[Enemy] = []
        self.spawn_timer = 0.0
        self.failed_connection_lookups: dict[str, int] = {}
        self.wikipedia_retry_timer = 0.0
        self.state = "loading"
        self.notice = "Finding a random person on Wikipedia..."
        self.notice_time = 0.0

        unfinished_defeats = [
            name
            for name in self.defeated_people
            if not self.people_graph[name]["connections_loaded"]
        ]

        # Resume cached progress with one opponent. Finish interrupted defeated
        # profiles before introducing an unrelated random root.
        if self.possible_enemies:
            self.spawn_person(random.choice(sorted(self.possible_enemies)))
            self.spawn_timer = SPAWN_INTERVAL
            self.state = "playing"
        elif unfinished_defeats:
            self.notice = f"Resuming {len(unfinished_defeats)} connection lookups..."
        else:
            self.request_random_person()

        # A lookup interrupted in an earlier run is safe to resume: its defeated
        # source can never be spawned again, but its connections are still useful.
        for name in unfinished_defeats:
            self.request_connections(name)

    def save_progress(self) -> None:
        wiki_api.save_to_graph(
            self.people_graph,
            roots=self.tree_roots,
            pending=self.possible_enemies,
            defeated=self.defeated_people,
        )

    def request_random_person(self, *, exclude_known: bool = False) -> None:
        if any(kind == "random" for kind, _, _ in self.wiki_tasks.values()):
            return
        excluded = set(self.defeated_people)
        if exclude_known:
            excluded.update(self.possible_enemies)
            excluded.update(self.active_people)
        task = self.wiki_loop.create_task(
            wiki_api.find_random_person(excluded)
        )
        self.wiki_tasks[task] = ("random", None, 0)

    def request_connections(self, name: str, depth: int = 1) -> None:
        if any(
            kind == "connections" and source == name
            for kind, source, _ in self.wiki_tasks.values()
        ):
            return
        task = self.wiki_loop.create_task(
            wiki_api.get_connected_people(name, depth=depth)
        )
        self.wiki_tasks[task] = ("connections", name, depth)

    def ensure_person(self, name: str) -> dict[str, object]:
        return self.people_graph.setdefault(
            name,
            {
                "connections": [],
                "connections_loaded": False,
                "defeated": False,
            },
        )

    def register_person(self, name: str, *, root: bool = False) -> None:
        self.ensure_person(name)
        if root and name not in self.tree_roots:
            self.tree_roots.append(name)
        if name not in self.defeated_people:
            self.possible_enemies.add(name)

    def poll_wikipedia(self) -> None:
        """Give async HTTP requests a non-blocking turn, then collect results."""
        if not self.wiki_tasks:
            return
        self.wiki_loop.run_until_complete(asyncio.sleep(0))
        for task, (kind, source, depth) in list(self.wiki_tasks.items()):
            if not task.done():
                continue
            del self.wiki_tasks[task]
            try:
                result = task.result()
            except asyncio.CancelledError:
                continue
            except Exception as error:
                print(f"Wikipedia {kind} lookup failed: {error}")
                self.notice_time = 4.0
                if kind == "random" and not self.enemies:
                    self.notice = "Wikipedia lookup failed — press R to retry"
                    self.state = "error"
                elif source is not None:
                    self.failed_connection_lookups[source] = depth
                    self.wikipedia_retry_timer = 6.0
                    self.notice = "Connection lookup failed — retrying shortly"
                continue

            if kind == "random":
                name = str(result)
                self.register_person(name, root=True)
                self.save_progress()
                if self.state == "loading" and not self.enemies:
                    self.spawn_person(name)
                    self.spawn_timer = SPAWN_INTERVAL
                    self.state = "playing"
                    self.notice = f"Your first opponent: {name}"
                else:
                    self.spawn_timer = min(self.spawn_timer, 0.45)
                    self.notice = f"New random opponent unlocked: {name}"
                self.notice_time = 2.8
                continue

            if source is None:
                continue
            connections = {str(name) for name in result if str(name) != source}
            usable_connections = connections - self.defeated_people
            if not usable_connections and depth == 1:
                self.request_connections(source, depth=2)
                self.notice = f"No direct connections for {source} — searching 2 hops"
                self.notice_time = 3.0
                continue
            if not usable_connections:
                self.people_graph[source]["connections"] = sorted(
                    connections, key=str.casefold
                )
                self.people_graph[source]["connections_loaded"] = True
                for name in connections:
                    self.ensure_person(name)
                self.save_progress()
                if source in self.defeated_people:
                    self.request_random_person(exclude_known=True)
                    self.notice = (
                        f"No connections for {source} — finding a random person"
                    )
                else:
                    self.notice = f"No connections found for {source}"
                self.notice_time = 3.0
                continue
            self.people_graph[source]["connections"] = sorted(
                connections, key=str.casefold
            )
            self.people_graph[source]["connections_loaded"] = True
            for name in connections:
                self.ensure_person(name)
            if source in self.defeated_people:
                for name in connections:
                    self.register_person(name)
                self.spawn_timer = min(self.spawn_timer, 0.45)
                if self.state == "loading" and not self.enemies:
                    self.spawn_person(random.choice(sorted(self.possible_enemies)))
                    self.spawn_timer = SPAWN_INTERVAL
                    self.state = "playing"
                self.notice = (
                    f"{len(usable_connections)} people connected to {source} unlocked"
                )
            else:
                self.notice = f"Connections for {source} are ready"
            self.save_progress()
            self.notice_time = 3.0

    def retry_failed_connections(self, dt: float) -> None:
        if not self.failed_connection_lookups:
            return
        self.wikipedia_retry_timer = max(0.0, self.wikipedia_retry_timer - dt)
        if self.wikipedia_retry_timer > 0:
            return
        lookups = self.failed_connection_lookups
        self.failed_connection_lookups = {}
        for name, depth in lookups.items():
            self.request_connections(name, depth=depth)

    def edge_spawn_position(self, radius: int) -> pygame.Vector2:
        """Choose a point just inside one of the four arena edges."""
        side = random.choice(("top", "right", "bottom", "left"))
        if side == "top":
            return pygame.Vector2(
                random.uniform(ARENA.left + radius, ARENA.right - radius),
                ARENA.top + radius,
            )
        if side == "bottom":
            return pygame.Vector2(
                random.uniform(ARENA.left + radius, ARENA.right - radius),
                ARENA.bottom - radius,
            )
        if side == "left":
            return pygame.Vector2(
                ARENA.left + radius,
                random.uniform(ARENA.top + radius, ARENA.bottom - radius),
            )
        return pygame.Vector2(
            ARENA.right - radius,
            random.uniform(ARENA.top + radius, ARENA.bottom - radius),
        )

    def spawn_person(self, name: str) -> None:
        """Spawn an unlocked, undefeated person once, at an arena edge."""
        if name in self.defeated_people or name in self.active_people:
            return
        person = self.ensure_person(name)
        is_boss = name.casefold() in {"adolf hitler", "hitler"}
        radius = 30 if is_boss else 12
        enemy = Enemy(
            self.edge_spawn_position(radius),
            name,
            ARENA,
            radius=radius,
            max_health=130 if is_boss else 38,
            speed=78 if is_boss else 58 + sum(map(ord, name)) % 19,
            boss=is_boss,
        )
        self.enemies.append(enemy)
        self.active_people.add(name)
        if not person["connections_loaded"]:
            self.request_connections(name)

    def record_new_defeats(self) -> None:
        for enemy in self.enemies:
            name = enemy.name
            if enemy.alive or name in self.defeated_people:
                continue
            self.defeated_people.add(name)
            self.possible_enemies.discard(name)
            self.active_people.discard(name)
            self.ensure_person(name)["defeated"] = True

            cached_connections = self.people_graph[name]["connections"]
            if not self.people_graph[name]["connections_loaded"]:
                self.request_connections(name)
                self.notice = f"Connections for {name} are still loading..."
            elif not (set(cached_connections) - self.defeated_people):
                self.request_random_person(exclude_known=True)
                self.notice = f"No connections for {name} — finding a random person"
            else:
                for connected_name in cached_connections:
                    self.register_person(connected_name)
                self.notice = f"People connected to {name} are now possible enemies"
                self.spawn_timer = min(self.spawn_timer, 0.45)
            self.save_progress()
            self.notice_time = 2.8

            if name.casefold() in {"adolf hitler", "hitler"}:
                self.state = "won"

    def spawn_from_possible_people(self, dt: float) -> None:
        self.spawn_timer = max(0.0, self.spawn_timer - dt)
        living_count = sum(enemy.alive for enemy in self.enemies)
        if living_count >= MAX_ACTIVE_ENEMIES or self.spawn_timer > 0:
            return
        eligible = self.possible_enemies - self.active_people - self.defeated_people
        if not eligible:
            return
        self.spawn_person(random.choice(sorted(eligible)))
        self.spawn_timer = SPAWN_INTERVAL

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
        processed_impacts: set[tuple[int, int]] = set()
        for _ in range(12):
            corrected_overlap = False
            for index, entity in enumerate(entities):
                for other in entities[index + 1 :]:
                    pair = (id(entity), id(other))
                    collided = entity.separate_from(
                        other, apply_impact=pair not in processed_impacts
                    )
                    if collided:
                        processed_impacts.add(pair)
                        corrected_overlap = True
            if not corrected_overlap:
                break

    def update(self, dt: float) -> None:
        self.poll_wikipedia()
        self.retry_failed_connections(dt)
        if self.state != "playing":
            return

        self.spawn_from_possible_people(dt)
        self.player.update(dt, pygame.key.get_pressed(), self.enemies)
        for enemy in self.enemies:
            enemy.update(dt, self.player)
        self.resolve_entity_collisions()

        self.player.attack(self.enemies)
        for enemy in self.enemies:
            if enemy.alive:
                enemy.attack((self.player,))
        self.resolve_entity_collisions()
        self.record_new_defeats()
        self.enemies = [
            enemy for enemy in self.enemies if not enemy.ready_to_despawn
        ]

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

    def draw_waiting_list(self) -> None:
        panel = pygame.Rect(
            PLAYFIELD_WIDTH + 14, 18, WIDTH - PLAYFIELD_WIDTH - 28, HEIGHT - 36
        )
        pygame.draw.rect(self.screen, (225, 218, 198), panel, border_radius=12)
        pygame.draw.rect(self.screen, INK, panel, 2, border_radius=12)

        waiting = sorted(
            self.possible_enemies - self.active_people - self.defeated_people,
            key=str.casefold,
        )
        heading = self.font.render("WAITING TO FIGHT", True, INK)
        self.screen.blit(heading, (panel.left + 16, panel.top + 16))
        summary = self.small_font.render(
            f"{len(waiting)} waiting   {len(self.defeated_people)} defeated",
            True,
            INK,
        )
        self.screen.blit(summary, (panel.left + 16, panel.top + 45))

        first_y = panel.top + 76
        line_height = 23
        visible_count = max(0, (panel.bottom - first_y - 28) // line_height)
        for index, name in enumerate(waiting[:visible_count]):
            available_width = panel.width - 44
            display_name = name
            while (
                len(display_name) > 3
                and self.small_font.size(display_name)[0] > available_width
            ):
                display_name = display_name[:-2]
            if display_name != name:
                display_name = display_name.rstrip() + "…"
            label = self.small_font.render(f"{index + 1}. {display_name}", True, INK)
            self.screen.blit(label, (panel.left + 16, first_y + index * line_height))

        hidden_count = len(waiting) - visible_count
        if hidden_count > 0:
            more = self.small_font.render(f"+ {hidden_count} more", True, INK)
            self.screen.blit(more, (panel.left + 16, panel.bottom - 27))

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
            "Goal: follow Wikipedia connections and defeat Hitler", True, INK
        )
        self.screen.blit(objective, (175, 27))
        self.draw_waiting_list()

        self.draw_bar(
            pygame.Rect(PLAYFIELD_WIDTH - 254, 20, 220, 24),
            self.player.health / 100,
            (90, 184, 104),
            f"HEALTH  {round(self.player.health)}",
        )
        self.draw_bar(
            pygame.Rect(42, HEIGHT - 27, 154, 18),
            self.player.charge["left"] / self.player.charge_limit,
            (229, 70, 153) if self.player.can_overcharge else (102, 171, 224),
            "J  OVERCHARGE" if self.player.can_overcharge else "J  LEFT PUNCH",
        )
        self.draw_bar(
            pygame.Rect(204, HEIGHT - 27, 154, 18),
            self.player.charge["right"] / self.player.charge_limit,
            (229, 70, 153) if self.player.can_overcharge else (102, 171, 224),
            "K  OVERCHARGE" if self.player.can_overcharge else "K  RIGHT PUNCH",
        )
        controls = self.small_font.render(
            "W/S move   Shift lock   A/D turn/strafe   Q/E turn/dash   J/K punch   U/I kick",
            True,
            INK,
        )
        self.screen.blit(
            controls,
            controls.get_rect(bottomright=(PLAYFIELD_WIDTH - 40, HEIGHT - 9)),
        )

        if self.player.can_overcharge and self.state == "playing":
            warning = self.small_font.render(
                "DESPERATION: OVERCHARGE UNLOCKED — charging heavily slows movement",
                True,
                (178, 34, 104),
            )
            self.screen.blit(
                warning, warning.get_rect(midtop=(PLAYFIELD_WIDTH / 2, 49))
            )

        if self.notice_time > 0 and self.state == "playing":
            message = self.font.render(self.notice, True, INK)
            box = message.get_rect(center=(PLAYFIELD_WIDTH / 2, 100)).inflate(24, 14)
            pygame.draw.rect(self.screen, PAPER, box, border_radius=8)
            pygame.draw.rect(self.screen, INK, box, 2, border_radius=8)
            self.screen.blit(message, message.get_rect(center=box.center))

        if self.state in {"won", "lost", "error", "loading"}:
            veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            veil.fill((25, 28, 36, 170))
            self.screen.blit(veil, (0, 0))
            headline = {
                "won": "YOU WIN!",
                "lost": "KNOCKED OUT",
                "error": "WIKIPEDIA UNAVAILABLE",
                "loading": "SEARCHING WIKIPEDIA...",
            }[self.state]
            text = self.big_font.render(headline, True, PAPER)
            self.screen.blit(
                text,
                text.get_rect(center=(PLAYFIELD_WIDTH / 2, HEIGHT / 2 - 25)),
            )
            if self.state != "loading":
                restart = self.font.render("Press R to try again", True, PAPER)
                self.screen.blit(
                    restart,
                    restart.get_rect(center=(PLAYFIELD_WIDTH / 2, HEIGHT / 2 + 35)),
                )

        pygame.display.flip()

    def run(self) -> None:
        running = True
        smoke_frames = int(os.environ.get("KILIN_KOLIN_SMOKE_FRAMES", "0"))
        frames = 0
        while running:
            # Cap long frames so boosted movement cannot skip through small bodies.
            dt = min(self.clock.tick(FPS) / 1000, 1 / 30)
            for event in pygame.event.get():
                running = self.handle_event(event) and running
            self.update(dt)
            self.draw()
            frames += 1
            if smoke_frames and frames >= smoke_frames:
                running = False
        tasks = list(self.wiki_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            # One loop turn delivers cancellation without making Quit wait for an
            # in-flight HTTP timeout.
            self.wiki_loop.run_until_complete(asyncio.sleep(0))
        self.wiki_loop.close()
        pygame.quit()


if __name__ == "__main__":
    Game().run()
