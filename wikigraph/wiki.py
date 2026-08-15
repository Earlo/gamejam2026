import wikipediaapi
import asyncio

wiki = wikipediaapi.AsyncWikipedia(
    user_agent="6 degrees of separation - game (gamejam@visapollari.fi)",
    language="en"
)


async def find_random_person():
    while True:
        random_pages = await wiki.random(limit=1)
        title, page = next(iter(random_pages.items()))

        print("Random page title:", title)

        categories = await page.categories

        if await is_person_page(title):
            return title

async def is_person_page(title: str) -> bool:
    page = wiki.page(title)
    categories = await page.categories
    return (
        "Category:Living people" in categories
        or any("births" in s.lower() for s in categories)
    )


async def get_connected_people(person_name: str, depth: int = 1) -> set[str]:
    connected_people = set()
    visited = set()

    async def dfs(current_person: str, current_depth: int):
        if current_depth >= depth or current_person in visited:
            return

        visited.add(current_person)

        page = wiki.page(current_person)
        links = await page.links

        for link_title in links:
            if await is_person_page(link_title):
                print(f"Found connected person: {link_title} (depth {current_depth + 1})")
                connected_people.add(link_title)
            await dfs(link_title, current_depth + 1)

    await dfs(person_name, 0)
    return connected_people


async def main():
    person = await find_random_person()
    print(f"Random person: {person}")

    connected_people = await get_connected_people(person, depth=1)
    print(f"people connected to {person} are: {connected_people}")


if __name__ == "__main__":
    asyncio.run(main())