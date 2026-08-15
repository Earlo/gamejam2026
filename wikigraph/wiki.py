"""Wikipedia lookups and persistent graph storage for Kilin Kolin."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any

import wikipediaapi


SAVE_PATH = Path(__file__).with_name("save.json")
USER_AGENT = "6 degrees of separation - game (gamejam@visapollari.fi)"

wiki = wikipediaapi.AsyncWikipedia(user_agent=USER_AGENT, language="en")


def _empty_person() -> dict[str, Any]:
    return {
        "connections": [],
        "connections_loaded": False,
        "article_length": 0,
        "article_loaded": False,
        "stat_points": {},
        "defeated": False,
    }


def load_progress(path: Path = SAVE_PATH) -> dict[str, Any]:
    """Load a tree save, migrating the prototype's old flat record list."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        raw = {}

    graph: dict[str, dict[str, Any]] = {}
    roots: list[str] = []

    if isinstance(raw, dict) and isinstance(raw.get("trees"), list):
        defeated = {
            name for name in raw.get("allDefeated", []) if isinstance(name, str)
        }
        pending = {
            name for name in raw.get("allPending", []) if isinstance(name, str)
        }

        def read_node(node: object, *, is_root: bool = False) -> None:
            if not isinstance(node, dict):
                return
            name = node.get("name")
            if not isinstance(name, str) or not name:
                return
            if is_root and name not in roots:
                roots.append(name)
            children = node.get("connections", {})
            if not isinstance(children, dict):
                children = {}
            child_names = {
                child_name
                for child_name in children
                if isinstance(child_name, str) and child_name
            }
            person = graph.setdefault(name, _empty_person())
            person["connections"] = sorted(
                set(person["connections"]) | child_names, key=str.casefold
            )
            person["connections_loaded"] = bool(
                person["connections_loaded"]
                or node.get("connectionsLoaded", bool(children))
            )
            article_length = node.get("articleLength", 0)
            if isinstance(article_length, (int, float)) and article_length >= 0:
                person["article_length"] = max(
                    person["article_length"], int(article_length)
                )
            person["article_loaded"] = bool(
                person["article_loaded"] or node.get("articleLoaded", False)
            )
            if isinstance(node.get("stats"), dict):
                person["stat_points"] = dict(node["stats"])
            person["defeated"] = bool(
                person["defeated"] or node.get("defeated", False) or name in defeated
            )
            for child in children.values():
                read_node(child)

        for tree in raw["trees"]:
            read_node(tree, is_root=True)
        for name in defeated | pending:
            person = graph.setdefault(name, _empty_person())
            person["defeated"] = name in defeated
        return {
            "people": graph,
            "roots": roots,
            "defeated": defeated,
            "pending": pending - defeated,
        }

    # Legacy migration: infer roots from records that are not anyone's child.
    records = raw.get("people", raw) if isinstance(raw, dict) else raw
    if isinstance(records, dict):
        records = [
            dict(value, name=name)
            for name, value in records.items()
            if isinstance(value, Mapping)
        ]
    if not isinstance(records, list):
        records = []
    children: set[str] = set()
    for record in records:
        if isinstance(record, str):
            graph[record] = _empty_person()
            continue
        if not isinstance(record, dict):
            continue
        name = record.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        raw_connections = record.get("connections")
        connections = (
            sorted(
                {
                    item
                    for item in raw_connections
                    if isinstance(item, str) and item
                },
                key=str.casefold,
            )
            if isinstance(raw_connections, list)
            else []
        )
        children.update(connections)
        graph[name] = {
            "connections": connections,
            "connections_loaded": isinstance(raw_connections, list),
            "article_length": 0,
            "article_loaded": False,
            "stat_points": {},
            "defeated": bool(record.get("defeated", False)),
        }
    for child in children:
        graph.setdefault(child, _empty_person())
    roots = sorted(set(graph) - children, key=str.casefold)
    if graph and not roots:
        roots = [min(graph, key=str.casefold)]
    defeated = {name for name, person in graph.items() if person["defeated"]}
    return {
        "people": graph,
        "roots": roots,
        "defeated": defeated,
        "pending": set(graph) - defeated,
    }


def load_graph(path: Path = SAVE_PATH) -> dict[str, dict[str, Any]]:
    """Compatibility helper returning the flattened people index."""
    return load_progress(path)["people"]


def save_to_graph(
    graph: Mapping[str, Mapping[str, Any]],
    path: Path = SAVE_PATH,
    *,
    roots: Collection[str] = (),
    pending: Collection[str] | None = None,
    defeated: Collection[str] | None = None,
) -> None:
    """Persist aggregate progress and a nested forest without null connections."""
    defeated_names = set(defeated) if defeated is not None else {
        name for name, person in graph.items() if person.get("defeated", False)
    }
    pending_names = set(pending) if pending is not None else set(graph) - defeated_names
    expanded_nodes: set[str] = set()

    def make_node(name: str, ancestors: frozenset[str]) -> dict[str, Any]:
        person = graph.get(name, {})
        if name in ancestors or name in expanded_nodes:
            return {
                "name": name,
                "defeated": name in defeated_names,
                "connectionsLoaded": bool(person.get("connections_loaded", False)),
                "articleLength": max(0, int(person.get("article_length", 0))),
                "articleLoaded": bool(person.get("article_loaded", False)),
                "stats": dict(person.get("stat_points", {})),
                "connections": {},
            }
        expanded_nodes.add(name)
        connection_names = person.get("connections", [])
        if not isinstance(connection_names, (list, set, tuple)):
            connection_names = []
        next_ancestors = ancestors | {name}
        connections = {}
        for child_name in sorted(set(connection_names), key=str.casefold):
            if not isinstance(child_name, str) or not child_name:
                continue
            connections[child_name] = make_node(child_name, next_ancestors)
        return {
            "name": name,
            "defeated": name in defeated_names,
            "connectionsLoaded": bool(person.get("connections_loaded", False)),
            "articleLength": max(0, int(person.get("article_length", 0))),
            "articleLoaded": bool(person.get("article_loaded", False)),
            "stats": dict(person.get("stat_points", {})),
            "connections": connections,
        }

    root_names = list(dict.fromkeys(name for name in roots if name in graph))
    reachable: set[str] = set()

    def mark_reachable(name: str) -> None:
        if name in reachable:
            return
        reachable.add(name)
        for child in graph.get(name, {}).get("connections", []):
            if isinstance(child, str):
                mark_reachable(child)

    for root in root_names:
        mark_reachable(root)
    root_names.extend(
        sorted(set(graph) - reachable - set(root_names), key=str.casefold)
    )
    data = {
        "allDefeated": sorted(defeated_names, key=str.casefold),
        "allPending": sorted(pending_names - defeated_names, key=str.casefold),
        "trees": [make_node(name, frozenset()) for name in root_names],
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary_path.replace(path)


async def is_person_page(title: str) -> bool:
    """Return whether Wikipedia categories identify the page as a person."""
    categories = await wiki.page(title).categories
    return "Category:Living people" in categories or any(
        "births" in category.lower() for category in categories
    )


async def find_random_person(excluded: Collection[str] = ()) -> str:
    """Find a random biography that is not already defeated."""
    excluded_names = {name.casefold() for name in excluded}
    while True:
        random_pages = await wiki.random(limit=1)
        title = next(iter(random_pages))
        if title.casefold() not in excluded_names and await is_person_page(title):
            return title


async def get_article_lengths(titles: Collection[str]) -> dict[str, int]:
    """Fetch Wikipedia's article byte lengths with bounded concurrency."""
    semaphore = asyncio.Semaphore(10)

    async def fetch(title: str) -> tuple[str, int]:
        try:
            async with semaphore:
                length = await wiki.page(title).length
            return title, max(0, int(length))
        except Exception:
            return title, 0

    return dict(await asyncio.gather(*(fetch(title) for title in titles)))


async def _people_among(titles: Collection[str]) -> set[str]:
    """Check linked pages concurrently without flooding Wikipedia."""
    semaphore = asyncio.Semaphore(12)

    async def check(title: str) -> str | None:
        async with semaphore:
            return title if await is_person_page(title) else None

    results = await asyncio.gather(
        *(check(title) for title in titles), return_exceptions=True
    )
    # A deleted, protected, or temporarily unavailable linked page must not make
    # an otherwise valid search retry forever.
    return {title for title in results if isinstance(title, str)}


async def _links_from(titles: Collection[str]) -> set[str]:
    """Collect links from a page set concurrently, including non-person pages."""
    semaphore = asyncio.Semaphore(12)

    async def links(title: str) -> set[str]:
        async with semaphore:
            return set(await wiki.page(title).links)

    results = await asyncio.gather(
        *(links(title) for title in titles), return_exceptions=True
    )
    return set().union(
        *(result for result in results if isinstance(result, set))
    )


async def get_connected_people(person_name: str, depth: int = 1) -> set[str]:
    """Return biography pages linked directly from a person's article."""
    if depth <= 0:
        return set()
    link_titles = await _links_from({person_name})
    connected_people = await _people_among(link_titles - {person_name})
    connected_people.discard(person_name)
    return connected_people


async def main() -> None:
    person = await find_random_person()
    print(f"Random person: {person}")
    connected_people = await get_connected_people(person)
    print(f"People connected to {person}: {sorted(connected_people)}")


if __name__ == "__main__":
    asyncio.run(main())
