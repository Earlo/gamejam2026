"""Regression tests for persistent enemy victories and assists."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from entities import Enemy, Player
from game import ARENA, Game
from wikigraph import wiki as wiki_api


class PlayerDefeatHistoryTests(unittest.TestCase):
    def make_enemy(self, name: str) -> Enemy:
        return Enemy((200, 200), name, ARENA, threat_level=0)

    @staticmethod
    def make_game(enemies: list[Enemy]) -> Game:
        game = Game.__new__(Game)
        game.player = Player(ARENA)
        game.enemies = enemies
        game.people_graph = {}
        game.save_progress = lambda: None
        return game

    def test_final_blow_gets_gold_and_other_living_enemy_gets_silver(self) -> None:
        killer = self.make_enemy("Killer")
        assistant = self.make_enemy("Assistant")
        defeated_bystander = self.make_enemy("Already defeated")
        defeated_bystander.health = 0
        game = self.make_game([killer, assistant, defeated_bystander])

        game.player.take_damage(game.player.health, source=killer)
        # Later physics involving the ragdoll must not replace the final blow.
        game.player.take_damage(1, source=assistant)
        game.record_player_defeat()

        self.assertEqual(game.people_graph["Killer"]["defeated_player"], 1)
        self.assertEqual(game.people_graph["Killer"]["assisted_defeat"], 0)
        self.assertEqual(game.people_graph["Assistant"]["defeated_player"], 0)
        self.assertEqual(game.people_graph["Assistant"]["assisted_defeat"], 1)
        self.assertNotIn("Already defeated", game.people_graph)

    def test_environmental_final_blow_gives_living_enemies_assists(self) -> None:
        first = self.make_enemy("First")
        second = self.make_enemy("Second")
        game = self.make_game([first, second])

        game.player.take_damage(game.player.health)
        game.record_player_defeat()

        for name in ("First", "Second"):
            self.assertEqual(game.people_graph[name]["defeated_player"], 0)
            self.assertEqual(game.people_graph[name]["assisted_defeat"], 1)

    def test_star_colors_include_every_gold_and_silver_result(self) -> None:
        self.assertEqual(
            Enemy.defeat_star_colors(2, 3),
            [Enemy.FINAL_BLOW_STAR_COLOR] * 2
            + [Enemy.ASSIST_STAR_COLOR] * 3,
        )

    def test_counters_round_trip_through_save_json(self) -> None:
        graph = {
            "Opponent": {
                "connections": [],
                "connections_loaded": True,
                "article_length": 10,
                "article_loaded": True,
                "stat_points": {},
                "defeated": False,
                "defeated_player": 2,
                "assisted_defeat": 3,
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "save.json"
            wiki_api.save_to_graph(
                graph, path, roots=["Opponent"], pending=["Opponent"]
            )

            raw = json.loads(path.read_text(encoding="utf-8"))
            node = raw["trees"][0]
            self.assertEqual(node["defeatedPlayer"], 2)
            self.assertEqual(node["assistedDefeat"], 3)

            loaded = wiki_api.load_progress(path)["people"]["Opponent"]
            self.assertEqual(loaded["defeated_player"], 2)
            self.assertEqual(loaded["assisted_defeat"], 3)

    def test_old_save_nodes_default_both_counters_to_zero(self) -> None:
        old_save = {
            "allDefeated": [],
            "allPending": ["Opponent"],
            "trees": [
                {
                    "name": "Opponent",
                    "defeated": False,
                    "connections": {},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "save.json"
            path.write_text(json.dumps(old_save), encoding="utf-8")

            loaded = wiki_api.load_progress(path)["people"]["Opponent"]
            self.assertEqual(loaded["defeated_player"], 0)
            self.assertEqual(loaded["assisted_defeat"], 0)


if __name__ == "__main__":
    unittest.main()
