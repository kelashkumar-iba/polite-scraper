import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, HttpUrl, ValidationError

# --- Politeness settings -----------------------------------------------

USER_AGENT = "FlyRankInternshipA9/1.0 (+https://github.com/kelashkumar-iba/polite-scraper)"
TIMEOUT_SECONDS = 10
DELAY_SECONDS = 0.5
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "cache")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

BASE_CATALOGUE_URL = "https://books.toscrape.com/catalogue/page-1.html"
MAX_CATALOGUE_PAGES = 3

STAR_WORDS = {"Zero", "One", "Two", "Three", "Four", "Five"}
STAR_WORD_TO_NUMBER = {"Zero": 0, "One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


# ---------------------------------------------------------------------------
# Fetch + cache (unchanged from Stage 3)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Discovery (unchanged from Stage 3)
# ---------------------------------------------------------------------------

def get_book_links(html: str, page_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for article in soup.select("article.product_pod"):
        a_tag = article.select_one("h3 a")
        if a_tag and a_tag.get("href"):
            links.append(urljoin(page_url, a_tag["href"]))
    return links


def get_next_page_url(html: str, current_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    next_li = soup.select_one("li.next a")
    if next_li and next_li.get("href"):
        return urljoin(current_url, next_li["href"])
    return None


def discover_all_book_links() -> list[tuple[str, str]]:
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

    seen = {}
    for link, source in all_pairs:
        if link not in seen:
            seen[link] = source
    return list(seen.items())


def cache_filename_for_book(product_url: str) -> str:
    parts = product_url.rstrip("/").split("/")
    slug = parts[-2] if len(parts) >= 2 else parts[-1]
    return f"book-{slug}.html"


# ---------------------------------------------------------------------------
# Raw extraction (unchanged from Stage 3)
# ---------------------------------------------------------------------------

def extract_book_record(html: str, product_url: str, source_page: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
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
            for word in rating_el.get("class", []):
                if word in STAR_WORDS:
                    rating_text = word
                    break

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


# ---------------------------------------------------------------------------
# Stage 4: normalize raw text into clean values
# ---------------------------------------------------------------------------

def parse_price_gbp(price_text: str | None) -> float | None:
    """'£51.77' -> 51.77. Strips the currency symbol and any stray
    whitespace/encoding artifacts, then parses the number."""
    if not price_text:
        return None
    # Keep only digits and the decimal point.
    cleaned = re.sub(r"[^\d.]", "", price_text)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_rating_number(rating_text: str | None) -> int | None:
    if not rating_text:
        return None
    return STAR_WORD_TO_NUMBER.get(rating_text)


# ---------------------------------------------------------------------------
# Schema -- the shape of a finished, storable record.
# ---------------------------------------------------------------------------

class Book(BaseModel):
    title: str
    product_url: HttpUrl
    price_text: str
    price_gbp: float
    availability_text: str
    rating_text: str
    rating_number: int
    description: str | None
    source_page: HttpUrl
    fetched_at: str


def normalize_record(raw: dict) -> dict:
    """Takes a raw extracted record and returns a dict with the clean
    fields added alongside the original raw text -- both live side by
    side, nothing is thrown away."""
    return {
        **raw,
        "price_gbp": parse_price_gbp(raw.get("price_text")),
        "rating_number": parse_rating_number(raw.get("rating_text")),
    }


def main():
    link_pairs = discover_all_book_links()
    urls_only = [url for url, _ in link_pairs]
    print(f"catalogue_pages={min(MAX_CATALOGUE_PAGES, 3)}")
    print(f"discovered={len(urls_only)}")
    print(f"unique_urls={len(set(urls_only))}")

    valid_books = []
    invalid_records = []
    seen_canonical_urls = set()

    for product_url, source_page in link_pairs:
        # product_url is already the canonical identity of this record --
        # skip if we've somehow already processed it (shouldn't happen
        # given discover_all_book_links() already de-duplicates, but this
        # is the belt-and-suspenders check that guarantees idempotency).
        if product_url in seen_canonical_urls:
            continue
        seen_canonical_urls.add(product_url)

        cache_filename = cache_filename_for_book(product_url)
        html = fetch_page(product_url, cache_filename)
        raw = extract_book_record(html, product_url, source_page=source_page)
        normalized = normalize_record(raw)

        try:
            book = Book(**normalized)
            valid_books.append(json.loads(book.model_dump_json()))
        except ValidationError as e:
            invalid_records.append({
                "product_url": product_url,
                "reason": str(e),
                "raw_record": raw,
            })

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(os.path.join(OUTPUT_DIR, "books.json"), "w", encoding="utf-8") as f:
        json.dump(valid_books, f, indent=2, ensure_ascii=False)

    with open(os.path.join(OUTPUT_DIR, "errors.json"), "w", encoding="utf-8") as f:
        json.dump(invalid_records, f, indent=2, ensure_ascii=False)

    print(f"detail_pages={len(link_pairs)}")
    print(f"valid_records={len(valid_books)}")
    print(f"invalid_records={len(invalid_records)}")


if __name__ == "__main__":
    main()