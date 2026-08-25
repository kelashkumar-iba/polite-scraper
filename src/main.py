import os
import time
from datetime import datetime, timezone
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
    time.sleep(DELAY_SECONDS)
    return html


def get_book_links(html: str, page_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = []

    for article in soup.select("article.product_pod"):
        a_tag = article.select_one("h3 a")
        if a_tag and a_tag.get("href"):
            absolute_url = urljoin(page_url, a_tag["href"])
            links.append(absolute_url)

    return links


def get_next_page_url(html: str, current_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    next_li = soup.select_one("li.next a")

    if next_li and next_li.get("href"):
        return urljoin(current_url, next_li["href"])

    return None


def discover_all_book_links() -> list[tuple[str, str]]:
    """
    Returns a de-duplicated list of (product_url, source_page) pairs, so
    every book remembers exactly which catalogue page it was found on --
    that's part of each record's provenance.
    """
    all_pairs = []
    current_url = BASE_CATALOGUE_URL
    page_number = 1

    while current_url and page_number <= MAX_CATALOGUE_PAGES:
        cache_filename = f"catalogue-page-{page_number}.html"
        html = fetch_page(current_url, cache_filename)

        for link in get_book_links(html, current_url):
            all_pairs.append((link, current_url))

        current_url = get_next_page_url(html, current_url)
        page_number += 1

    # De-duplicate by product_url while keeping the first source_page seen.
    seen = {}
    for link, source in all_pairs:
        if link not in seen:
            seen[link] = source

    return list(seen.items())


# ---------------------------------------------------------------------------
# Stage 3: extract the eight raw fields from a single book detail page.
# ---------------------------------------------------------------------------

# star-rating class looks like: class="star-rating Three" -- the rating
# word is the second class, and there's no numeric attribute to read
# directly, so this word-list is just how the site encodes the number.
STAR_WORDS = {"Zero", "One", "Two", "Three", "Four", "Five"}


def cache_filename_for_book(product_url: str) -> str:
    """
    Turns a book's URL into a safe, unique cache filename, e.g.
    'a-light-in-the-attic_1000' from
    '.../catalogue/a-light-in-the-attic_1000/index.html'
    """
    parts = product_url.rstrip("/").split("/")
    slug = parts[-2] if len(parts) >= 2 else parts[-1]
    return f"book-{slug}.html"


def extract_book_record(html: str, product_url: str, source_page: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    # Aim at the product's main info block, not the whole document -- this
    # is what protects us if the page ever grows a second <h1> or price
    # somewhere else (related products, ads, etc).
    product_main = soup.select_one("div.product_main")

    title = None
    if product_main:
        h1 = product_main.select_one("h1")
        if h1:
            title = h1.get_text(strip=True)

    price_text = None
    if product_main:
        price_el = product_main.select_one("p.price_color")
        if price_el:
            price_text = price_el.get_text(strip=True)

    availability_text = None
    if product_main:
        avail_el = product_main.select_one("p.availability")
        if avail_el:
            availability_text = avail_el.get_text(strip=True)

    rating_text = None
    if product_main:
        rating_el = product_main.select_one("p.star-rating")
        if rating_el:
            classes = rating_el.get("class", [])
            for word in classes:
                if word in STAR_WORDS:
                    rating_text = word
                    break

    # Description sits in a <p> right after the #product_description div --
    # it has no dedicated class of its own, and some books simply don't
    # have one at all, in which case we store null rather than inventing text.
    description = None
    desc_heading = soup.select_one("#product_description")
    if desc_heading:
        desc_p = desc_heading.find_next_sibling("p")
        if desc_p:
            description = desc_p.get_text(strip=True)

    return {
        "title": title,
        "product_url": product_url,
        "price_text": price_text,
        "availability_text": availability_text,
        "rating_text": rating_text,
        "description": description,
        "source_page": source_page,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    link_pairs = discover_all_book_links()
    urls_only = [url for url, _ in link_pairs]
    print(f"catalogue_pages={min(MAX_CATALOGUE_PAGES, 3)}")
    print(f"discovered={len(urls_only)}")
    print(f"unique_urls={len(set(urls_only))}")

    records = []
    for product_url, source_page in link_pairs:
        cache_filename = cache_filename_for_book(product_url)
        html = fetch_page(product_url, cache_filename)
        record = extract_book_record(html, product_url, source_page=source_page)
        records.append(record)

    print(f"detail_pages={len(records)}")
    print("--- sample record ---")
    print(records[0])


if __name__ == "__main__":
    main()