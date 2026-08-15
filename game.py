"""A tiny, self-contained Kilin Kolin pygame prototype."""

from __future__ import annotations

import asyncio
import os
import random

import pygame

from entities import (
    DroppedItem,
    Enemy,
    Entity,
    Player,
    POWERUP_INFO,
    STAT_KEYS,
    WEAPON_SPECS,
    allocate_enemy_stats,
    enemy_combat_stats,
    enemy_threat_label,
)
from wikigraph import wiki as wiki_api


PLAYFIELD_WIDTH = 960
WIDTH, HEIGHT = 1280, 700
ARENA = pygame.Rect(34, 70, PLAYFIELD_WIDTH - 68, HEIGHT - 104)
FPS = 60
MAX_ACTIVE_ENEMIES = 8
DEFEATS_PER_ENEMY_SLOT = 5
MAX_CONCURRENT_CONNECTION_LOOKUPS = 2
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
        self.tiny_font = pygame.font.Font(None, 16)
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
        self.player.apply_defeat_progress(len(self.defeated_people))
        self.active_people: set[str] = set()
        self.people_waiting_for_stats: set[str] = set()
        self.profile_loading_people: set[str] = set()
        self.failed_article_profiles: set[str] = set()
        self.enemies: list[Enemy] = []
        self.dropped_items: list[DroppedItem] = []
        self.spawn_timer = 0.0
        self.failed_connection_lookups: dict[str, int] = {}
        self.connection_queue: dict[str, int] = {}
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
        self.request_article_lengths(self.possible_enemies)

    def save_progress(self) -> None:
        wiki_api.save_to_graph(
            self.people_graph,
            roots=self.tree_roots,
            pending=self.possible_enemies,
            defeated=self.defeated_people,
        )

    @property
    def active_enemy_limit(self) -> int:
        """Start at one opponent and earn another slot every five defeats."""
        return min(
            MAX_ACTIVE_ENEMIES,
            1 + self.player.defeat_count // DEFEATS_PER_ENEMY_SLOT,
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
        ) or name in self.connection_queue:
            return
        self.connection_queue[name] = depth

    def pump_connection_requests(self) -> None:
        active_count = sum(
            kind == "connections" for kind, _, _ in self.wiki_tasks.values()
        )
        while (
            self.connection_queue
            and active_count < MAX_CONCURRENT_CONNECTION_LOOKUPS
        ):
            name = min(
                self.connection_queue,
                key=lambda queued_name: (
                    queued_name not in self.active_people,
                    queued_name.casefold(),
                ),
            )
            depth = self.connection_queue.pop(name)
            task = self.wiki_loop.create_task(
                wiki_api.get_connected_people(name, depth=depth)
            )
            self.wiki_tasks[task] = ("connections", name, depth)
            active_count += 1

    def maybe_start_new_tree(self) -> bool:
        """Start a random root only after every current-tree enemy is exhausted."""
        connection_in_flight = any(
            kind == "connections" for kind, _, _ in self.wiki_tasks.values()
        )
        if (
            self.possible_enemies
            or self.active_people
            or self.people_waiting_for_stats
            or self.connection_queue
            or connection_in_flight
            or self.failed_connection_lookups
        ):
            return False
        self.request_random_person(exclude_known=True)
        return True

    def request_article_lengths(self, names: set[str]) -> None:
        candidates = sorted(
            (
                name
                for name in names
                if not self.ensure_person(name)["article_loaded"]
                and name not in self.profile_loading_people
                and name not in self.failed_article_profiles
            ),
            key=str.casefold,
        )[:32]
        if not candidates:
            return
        self.profile_loading_people.update(candidates)
        task = self.wiki_loop.create_task(wiki_api.get_article_lengths(candidates))
        self.wiki_tasks[task] = ("lengths", None, 0)

    def ensure_person(self, name: str) -> dict[str, object]:
        person = self.people_graph.setdefault(
            name,
            {
                "connections": [],
                "connections_loaded": False,
                "article_length": 0,
                "article_loaded": False,
                "stat_points": allocate_enemy_stats(name, 0),
                "defeated": False,
            },
        )
        person.setdefault("connections", [])
        person.setdefault("connections_loaded", False)
        person.setdefault("article_length", 0)
        person.setdefault("article_loaded", False)
        person.setdefault("stat_points", allocate_enemy_stats(name, 0))
        person.setdefault("defeated", False)
        saved_points = person["stat_points"]
        if not isinstance(saved_points, dict) or any(
            not isinstance(saved_points.get(stat), int) for stat in STAT_KEYS
        ):
            person["stat_points"] = allocate_enemy_stats(
                name, int(person["article_length"])
            )
        return person

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

            if kind == "lengths":
                lengths = dict(result)
                ready_to_spawn: list[str] = []
                for name, raw_length in lengths.items():
                    self.profile_loading_people.discard(name)
                    article_length = max(0, int(raw_length))
                    person = self.ensure_person(name)
                    person["article_length"] = article_length
                    person["article_loaded"] = article_length > 0
                    person["stat_points"] = allocate_enemy_stats(
                        name, article_length
                    )
                    if article_length <= 0:
                        self.failed_article_profiles.add(name)
                    if name in self.people_waiting_for_stats:
                        self.people_waiting_for_stats.discard(name)
                        ready_to_spawn.append(name)
                self.save_progress()
                for name in ready_to_spawn:
                    if (
                        sum(enemy.alive for enemy in self.enemies)
                        >= self.active_enemy_limit
                    ):
                        break
                    self.spawn_person(name)
                self.request_article_lengths(self.possible_enemies)
                continue

            if source is None:
                continue
            connections = {str(name) for name in result if str(name) != source}
            usable_connections = connections - self.defeated_people
            if not usable_connections:
                self.people_graph[source]["connections"] = sorted(
                    connections, key=str.casefold
                )
                self.people_graph[source]["connections_loaded"] = True
                for name in connections:
                    self.ensure_person(name)
                self.save_progress()
                if source in self.defeated_people:
                    if self.maybe_start_new_tree():
                        self.notice = (
                            f"Tree exhausted at {source} — starting a new tree"
                        )
                    else:
                        self.notice = f"No direct connections for {source}"
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
                self.request_article_lengths(usable_connections)
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
        if (
            name in self.defeated_people
            or name in self.active_people
            or name in self.people_waiting_for_stats
        ):
            return
        person = self.ensure_person(name)
        if not person["article_loaded"] and name not in self.failed_article_profiles:
            self.people_waiting_for_stats.add(name)
            self.request_article_lengths({name})
            return

        stat_points = dict(person["stat_points"])
        is_boss = name.casefold() in {"adolf hitler", "hitler"}
        combat_stats = enemy_combat_stats(stat_points, boss=is_boss)
        radius = int(combat_stats["radius"])
        enemy = Enemy(
            self.edge_spawn_position(radius),
            name,
            ARENA,
            radius=radius,
            max_health=float(combat_stats["max_health"]),
            speed=float(combat_stats["speed"]),
            turn_speed=float(combat_stats["turn_speed"]),
            damage_scale=float(combat_stats["damage_scale"]),
            aggression=int(combat_stats["aggression"]),
            attack_speed=int(combat_stats["attack_speed"]),
            threat_level=int(combat_stats["threat_level"]),
            stat_points=stat_points,
            article_length=int(person["article_length"]),
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
            self.player.gain_defeat_strength()
            self.drop_enemy_loot(enemy)
            self.ensure_person(name)["defeated"] = True

            cached_connections = self.people_graph[name]["connections"]
            branch_exhausted = bool(
                self.people_graph[name]["connections_loaded"]
                and not (set(cached_connections) - self.defeated_people)
            )
            if not self.people_graph[name]["connections_loaded"]:
                self.request_connections(name)
                self.notice = f"Connections for {name} are still loading..."
            elif branch_exhausted:
                self.notice = f"No direct connections for {name}"
            else:
                for connected_name in cached_connections:
                    self.register_person(connected_name)
                self.request_article_lengths(
                    set(cached_connections) - self.defeated_people
                )
                self.notice = f"People connected to {name} are now possible enemies"
                self.spawn_timer = min(self.spawn_timer, 0.45)
            self.save_progress()
            if branch_exhausted:
                if self.maybe_start_new_tree():
                    self.notice = f"Tree exhausted at {name} — starting a new tree"
            self.notice_time = 2.8

            if name.casefold() in {"adolf ", "hitler"}:
                self.state = "won"

    def drop_enemy_loot(self, enemy: Enemy) -> None:
        """Turn each defeat into a useful, visible arena reward."""
        weapon_chance = 0.18 + enemy.threat_level * 0.055
        guaranteed_early_weapon = self.player.defeat_count == 1
        if guaranteed_early_weapon or random.random() < weapon_chance:
            weapon_names = ["club"]
            if enemy.threat_level >= 1 or self.player.defeat_count >= 4:
                weapon_names.append("sword")
            if enemy.threat_level >= 3 or self.player.defeat_count >= 10:
                weapon_names.append("hammer")
            item = DroppedItem(
                enemy.pos,
                weapon_spec=WEAPON_SPECS[random.choice(weapon_names)],
            )
        else:
            # Low health strongly biases the useful drop without making the
            # other temporary combat boosts disappear from the loot table.
            choices = ["health", "health", "fury", "haste"]
            if self.player.health / self.player.max_health > 0.55:
                choices.remove("health")
            item = DroppedItem(enemy.pos, powerup=random.choice(choices))
        item.pos += pygame.Vector2(random.uniform(-12, 12), random.uniform(-12, 12))
        item.pos.x = Entity.clamp(item.pos.x, ARENA.left + 18, ARENA.right - 18)
        item.pos.y = Entity.clamp(item.pos.y, ARENA.top + 18, ARENA.bottom - 18)
        self.dropped_items.append(item)

    def update_dropped_items(self, dt: float) -> None:
        for item in self.dropped_items:
            item.update(dt)
            if self.player.alive and item.can_collect(self.player):
                message = item.collect(self.player)
                if message:
                    self.notice = message
                    self.notice_time = 2.2
        self.dropped_items = [
            item for item in self.dropped_items if not item.expired
        ][-14:]

    def spawn_from_possible_people(self, dt: float) -> None:
        self.spawn_timer = max(0.0, self.spawn_timer - dt)
        living_count = sum(enemy.alive for enemy in self.enemies)
        living_count += len(self.people_waiting_for_stats)
        if living_count >= self.active_enemy_limit or self.spawn_timer > 0:
            return
        eligible = (
            self.possible_enemies
            - self.active_people
            - self.defeated_people
            - self.people_waiting_for_stats
        )
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

    def resolve_entity_collisions(
        self,
        frame_start_positions: dict[Entity, pygame.Vector2] | None = None,
    ) -> None:
        """Resolve crossed paths and keep circular bodies from overlapping."""
        entities: list[Entity] = [self.player, *self.enemies]
        processed_impacts: set[tuple[int, int]] = set()
        for pass_index in range(12):
            corrected_overlap = False
            for index, entity in enumerate(entities):
                for other in entities[index + 1 :]:
                    pair = (id(entity), id(other))
                    if frame_start_positions is not None and pass_index == 0:
                        swept_collision = entity.resolve_swept_collision(
                            other,
                            frame_start_positions[entity],
                            frame_start_positions[other],
                            apply_impact=pair not in processed_impacts,
                        )
                        if swept_collision:
                            processed_impacts.add(pair)
                            corrected_overlap = True
                            continue
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
        self.pump_connection_requests()
        if self.state != "playing":
            return

        self.spawn_from_possible_people(dt)
        frame_start_positions = {
            entity: entity.pos.copy() for entity in [self.player, *self.enemies]
        }
        self.player.update(dt, pygame.key.get_pressed(), self.enemies)
        for enemy in self.enemies:
            enemy.update(dt, self.player)
        self.update_dropped_items(dt)
        self.resolve_entity_collisions(frame_start_positions)

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

    def draw_sidebar_person(
        self,
        panel: pygame.Rect,
        name: str,
        prefix: str,
        y: int,
    ) -> None:
        person = self.ensure_person(name)
        chart_text = "CHARTED" if person["connections_loaded"] else "SEARCHING"
        chart_color = (55, 125, 76) if person["connections_loaded"] else (174, 105, 42)
        chart_label = self.tiny_font.render(chart_text, True, chart_color)
        available_width = panel.width - 50 - chart_label.get_width()
        display_name = name
        while (
            len(display_name) > 3
            and self.small_font.size(prefix + display_name)[0] > available_width
        ):
            display_name = display_name[:-2]
        if display_name != name:
            display_name = display_name.rstrip() + "…"
        label = self.small_font.render(prefix + display_name, True, INK)
        self.screen.blit(label, (panel.left + 16, y))
        self.screen.blit(
            chart_label,
            (panel.right - 16 - chart_label.get_width(), y + 2),
        )

        points = person["stat_points"]
        total = sum(points[stat] for stat in STAT_KEYS)
        loading = "…" if not person["article_loaded"] else ""
        is_boss = name.casefold() in {"adolf hitler", "hitler"}
        threat = enemy_threat_label(points, boss=is_boss)
        stats_label = self.tiny_font.render(
            f"{threat} P{total}{loading}  HP{points['health']}  SP{points['speed']}  "
            f"DM{points['damage']}  TN{points['turn']}  AI{points['aggression']}  "
            f"AS{points['attack_speed']}",
            True,
            (76, 72, 68),
        )
        self.screen.blit(stats_label, (panel.left + 31, y + 18))

    def draw_waiting_list(self) -> None:
        panel = pygame.Rect(
            PLAYFIELD_WIDTH + 14, 18, WIDTH - PLAYFIELD_WIDTH - 28, HEIGHT - 36
        )
        pygame.draw.rect(self.screen, (225, 218, 198), panel, border_radius=12)
        pygame.draw.rect(self.screen, INK, panel, 2, border_radius=12)

        fighting = [enemy for enemy in self.enemies if enemy.alive]
        fighting_heading = self.font.render(
            f"CURRENTLY FIGHTING {len(fighting)}/{self.active_enemy_limit}",
            True,
            INK,
        )
        self.screen.blit(fighting_heading, (panel.left + 16, panel.top + 16))
        line_height = 36
        fighting_y = panel.top + 45
        for index, enemy in enumerate(fighting):
            self.draw_sidebar_person(
                panel, enemy.name, f"{index + 1}. ", fighting_y + index * line_height
            )

        waiting_heading_y = fighting_y + len(fighting) * line_height + 12
        pygame.draw.line(
            self.screen,
            (142, 137, 125),
            (panel.left + 16, waiting_heading_y - 8),
            (panel.right - 16, waiting_heading_y - 8),
        )
        waiting = sorted(
            self.possible_enemies - self.active_people - self.defeated_people,
            key=str.casefold,
        )
        heading = self.font.render("WAITING TO FIGHT", True, INK)
        self.screen.blit(heading, (panel.left + 16, waiting_heading_y))
        summary = self.small_font.render(
            f"{len(waiting)} waiting   {len(self.defeated_people)} defeated",
            True,
            INK,
        )
        self.screen.blit(summary, (panel.left + 16, waiting_heading_y + 29))
        player_power = self.tiny_font.render(
            f"PLAYER +{self.player.defeat_count}  ·  "
            f"ATTACK {self.player.attack_speed_multiplier:.2f}x",
            True,
            (68, 103, 151),
        )
        self.screen.blit(player_power, (panel.left + 16, waiting_heading_y + 48))
        legend = self.tiny_font.render(
            "HP health · SP speed · DM damage", True, (76, 72, 68)
        )
        self.screen.blit(legend, (panel.left + 16, waiting_heading_y + 64))
        legend_two = self.tiny_font.render(
            "TN turning · AI aggression · AS attack", True, (76, 72, 68)
        )
        self.screen.blit(legend_two, (panel.left + 16, waiting_heading_y + 78))

        first_y = waiting_heading_y + 100
        visible_count = max(0, (panel.bottom - first_y - 28) // line_height)
        for index, name in enumerate(waiting[:visible_count]):
            self.draw_sidebar_person(
                panel,
                name,
                f"{index + 1}. ",
                first_y + index * line_height,
            )

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

        for item in self.dropped_items:
            item.draw(self.screen, self.tiny_font)
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
            self.player.health / self.player.max_health,
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
        equipment_parts = []
        for side in Entity.SIDES:
            weapon = self.player.weapons[side]
            if weapon is not None:
                equipment_parts.append(
                    f"{side[0].upper()}:{weapon.name} {weapon.durability}"
                )
        for kind, remaining in self.player.powerup_timers.items():
            if remaining > 0:
                equipment_parts.append(
                    f"{POWERUP_INFO[kind][0].split()[0]} {remaining:.1f}s"
                )
        if equipment_parts:
            equipment = self.small_font.render(
                "   ".join(equipment_parts), True, INK
            )
            self.screen.blit(
                equipment,
                equipment.get_rect(midbottom=(PLAYFIELD_WIDTH / 2, HEIGHT - 34)),
            )
        controls = self.small_font.render(
            "W/S move   Shift lock   A/D turn/strafe   Q/E turn/dash   J/K punch/weapon   U/I kick",
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
