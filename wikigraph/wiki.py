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

        print("Categories:")
        for category in categories:
            print(" ", category)

        if "Category:Living people" in categories:
            return title


if __name__ == "__main__":
    person = asyncio.run(find_random_person())
    print(f"Random person: {person}")