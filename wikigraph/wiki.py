import wikipediaapi
import json
import asyncio

# Asynchronous client
wiki = wikipediaapi.AsyncWikipedia(user_agent='6 degrees of separation - game (gamejam@visapollari.fi)', language='en')

# save.json is a JSON array of objects, where there are people from wikipedia (just names) and as a child a list a people who they are connected to in wikipedia, and check if player has defeated that person or not.
def save_to_graph(graph):
    pass


async def find_random_person():
    person = None
    while person is None:
        # Get a random page from Wikipedia
        page = await wiki.random()
        print_categories(page)
        print("Random page title:", page)
        full_page = wiki.page(page)
        print("full_page:", full_page)
        category = await full_page.categories
        print("category:", category)
    return person

def find_connected_people():
    pass
    

async def print_categories(page):
    categories = await page.categories
    for title in sorted(categories.keys()):
        print("%s: %s" % (title, categories[title]))



if __name__ == "__main__":
    person = asyncio.run(find_random_person())
    print(f"Random person: {person}")