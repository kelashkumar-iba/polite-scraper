import os
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# --- Politeness settings -----------------------------------------------

USER_AGENT = "FlyRankInternshipA9/1.0 (+https://github.com/kelashkumar-iba/polite-scraper)"
TIMEOUT_SECONDS = 10
DELAY_SECONDS = 0.5
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "cache")

BASE_CATALOGUE_URL = "https://books.toscrape.com/catalogue/page-1.html"
MAX_CATALOGUE_PAGES = 3


def fetch_page(url: str, cache_filename: str) -> str:
    """
    Fetches a page politely, or reads it from the local cache if we've
    already fetched it before. Returns the raw HTML as a string.
    A real (non-cached) fetch is followed by a short delay -- cached reads
    never touch the network, so they need no delay.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, cache_filename)

    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            html = f.read()
        print(f"CACHE HIT  {cache_filename}  ({len(html)} bytes)")
        return html

    headers = {"User-Agent": USER_AGENT}
    response = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()

    html = response.text

    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"FETCH      {cache_filename}  ({len(html)} bytes)  status={response.status_code}")

    # Only real, live requests need to be polite about timing -- a cache
    # write only happens right after one, so this is the right place for it.
    time.sleep(DELAY_SECONDS)
    return html


def get_book_links(html: str, page_url: str) -> list[str]:
    """
    Parses a catalogue page and returns the absolute URL of every book
    listed on it.
    """
    soup = BeautifulSoup(html, "html.parser")
    links = []

    # Each book on a catalogue page sits inside an <article class="product_pod">
    # with an <h3><a href="..."> pointing at its detail page.
    for article in soup.select("article.product_pod"):
        a_tag = article.select_one("h3 a")
        if a_tag and a_tag.get("href"):
            relative_url = a_tag["href"]
            # Never glue strings together for this -- urljoin correctly
            # resolves ../book/index.html relative to the page it came from.
            absolute_url = urljoin(page_url, relative_url)
            links.append(absolute_url)

    return links


def get_next_page_url(html: str, current_url: str) -> str | None:
    """
    Looks for the catalogue's own "next" link and returns its absolute
    URL, or None if there isn't one (i.e. we're on the last page).
    """
    soup = BeautifulSoup(html, "html.parser")
    next_li = soup.select_one("li.next a")

    if next_li and next_li.get("href"):
        return urljoin(current_url, next_li["href"])

    return None


def discover_all_book_links() -> list[str]:
    """
    Walks the catalogue starting at page 1, following "next" links, up to
    MAX_CATALOGUE_PAGES pages. Returns a de-duplicated list of every book's
    absolute detail-page URL found along the way.
    """
    all_links = []
    current_url = BASE_CATALOGUE_URL
    page_number = 1

    while current_url and page_number <= MAX_CATALOGUE_PAGES:
        cache_filename = f"catalogue-page-{page_number}.html"
        html = fetch_page(current_url, cache_filename)

        page_links = get_book_links(html, current_url)
        all_links.extend(page_links)

        current_url = get_next_page_url(html, current_url)
        page_number += 1

    # Remove duplicates while keeping the list a plain list (not a set),
    # since order doesn't matter here but a stable, readable list does.
    unique_links = list(dict.fromkeys(all_links))

    return unique_links


def main():
    links = discover_all_book_links()
    pages_visited = min(MAX_CATALOGUE_PAGES, 3)

    print(f"catalogue_pages={pages_visited}")
    print(f"discovered={len(links)}")
    print(f"unique_urls={len(set(links))}")


if __name__ == "__main__":
    main()