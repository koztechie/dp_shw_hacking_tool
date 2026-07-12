import urllib.parse
from bs4 import BeautifulSoup
import httpx
from src.logger import logger

def search_itunes(query: str, limit: int = 3) -> list[dict]:
    url = f"https://itunes.apple.com/search?term={urllib.parse.quote(query)}&entity=software&limit={limit}"
    results = []
    try:
        response = httpx.get(url, timeout=10.0)
        if response.status_code == 200:
            data = response.json()
            for res in data.get("results", []):
                results.append({
                    "store": "Apple App Store",
                    "title": res.get("trackName"),
                    "description": res.get("description", "")[:200] + "...",
                    "url": res.get("trackViewUrl")
                })
    except Exception as e:
        logger.error(f"iTunes Search error: {e}")
    return results

def search_duckduckgo_play_store(query: str, limit: int = 3) -> list[dict]:
    # Search DDG for site:play.google.com/store/apps
    search_query = f"site:play.google.com/store/apps {query}"
    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    results = []
    try:
        response = httpx.post(url, data={"q": search_query}, headers=headers, timeout=10.0)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", class_="result__url", limit=limit):
                parent_div = a.find_parent("div")
                if not parent_div:
                    continue
                title_elem = parent_div.find("h2", class_="result__title")
                snippet_elem = parent_div.find("a", class_="result__snippet")
                
                title = title_elem.text.strip() if title_elem else ""
                snippet = snippet_elem.text.strip() if snippet_elem else ""
                link = a.get("href", "")
                
                if title:
                    results.append({
                        "store": "Google Play Store",
                        "title": title,
                        "description": snippet,
                        "url": link
                    })
    except Exception as e:
        logger.error(f"DDG Search error: {e}")
    return results

def check_existing_apps(keywords: str) -> list[dict]:
    """Returns a combined list of matching apps from App Store and Play Store."""
    logger.info(f"🔎 Опитування магазинів додатків для: '{keywords}'")
    apple_results = search_itunes(keywords, limit=3)
    play_results = search_duckduckgo_play_store(keywords, limit=3)
    return apple_results + play_results

if __name__ == "__main__":
    print(check_existing_apps("habit tracker rpg"))
