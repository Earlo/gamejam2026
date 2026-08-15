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
    return {"connections": None, "defeated": False}


def load_graph(path: Path = SAVE_PATH) -> dict[str, dict[str, Any]]:
    """Load the graph, accepting both current and early prototype formats."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}

    graph: dict[str, dict[str, Any]] = {}
    records = raw.get("people", raw) if isinstance(raw, dict) else raw
    if isinstance(records, dict):
        records = [dict(value, name=name) for name, value in records.items()]
    if not isinstance(records, list):
        return graph

    for record in records:
        if isinstance(record, str):
            graph[record] = _empty_person()
            continue
        if not isinstance(record, dict):
            continue
        name = record.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        connections = record.get("connections")
        if not isinstance(connections, list):
            connections = None
        else:
            connections = sorted(
                {item for item in connections if isinstance(item, str) and item},
                key=str.casefold,
            )
        graph[name] = {
            "connections": connections,
            "defeated": bool(record.get("defeated", False)),
        }
    return graph


def save_to_graph(
    graph: Mapping[str, Mapping[str, Any]], path: Path = SAVE_PATH
) -> None:
    """Persist discovered connections and defeat state with deterministic output."""
    records = []
    for name in sorted(graph, key=str.casefold):
        person = graph[name]
        connections = person.get("connections")
        records.append(
            {
                "name": name,
                "connections": (
                    sorted(set(connections), key=str.casefold)
                    if isinstance(connections, (list, set, tuple))
                    else None
                ),
                "defeated": bool(person.get("defeated", False)),
            }
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
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


async def _people_among(titles: Collection[str]) -> set[str]:
    """Check linked pages concurrently without flooding Wikipedia."""
    semaphore = asyncio.Semaphore(12)

    async def check(title: str) -> str | None:
        async with semaphore:
            return title if await is_person_page(title) else None

    results = await asyncio.gather(
        *(check(title) for title in titles), return_exceptions=True
    )
    failures = [result for result in results if isinstance(result, BaseException)]
    if failures:
        raise RuntimeError(
            f"Could not inspect {len(failures)} linked Wikipedia pages"
        ) from failures[0]
    return {title for title in results if isinstance(title, str)}


async def get_connected_people(person_name: str, depth: int = 1) -> set[str]:
    """Return biography pages linked from a person, up to ``depth`` hops away."""
    if depth <= 0:
        return set()

    connected_people: set[str] = set()
    visited: set[str] = set()
    frontier = {person_name}

    for _ in range(depth):
        link_titles: set[str] = set()
        for current_person in frontier - visited:
            visited.add(current_person)
            page_links = await wiki.page(current_person).links
            link_titles.update(page_links)

        if not link_titles:
            break
        people = await _people_among(link_titles - visited)
        connected_people.update(people)
        frontier = people

    connected_people.discard(person_name)
    return connected_people


async def main() -> None:
    person = await find_random_person()
    print(f"Random person: {person}")
    connected_people = await get_connected_people(person)
    print(f"People connected to {person}: {sorted(connected_people)}")


if __name__ == "__main__":
    asyncio.run(main())
