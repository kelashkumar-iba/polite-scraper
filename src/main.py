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
RETRY_DELAY_SECONDS = 2
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "cache")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

BASE_CATALOGUE_URL = "https://books.toscrape.com/catalogue/page-1.html"
MAX_CATALOGUE_PAGES = 3

# Set this to True to deliberately add one fake book URL to the list, to
# prove the scraper survives a broken page without crashing (Stage 5
# checkpoint). Leave False for a normal, real run.
INJECT_FAKE_URL_FOR_TESTING = True

STAR_WORDS = {"Zero", "One", "Two", "Three", "Four", "Five"}
STAR_WORD_TO_NUMBER = {"Zero": 0, "One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


class FetchFailure(Exception):
    """Raised when a page could not be fetched after retries. Carries the
    reason so the run report and error log can explain what happened."""
    def __init__(self, url, reason):
        self.url = url
        self.reason = reason
        super().__init__(f"{url}: {reason}")


# ---------------------------------------------------------------------------
# Fetch + cache, now with a retry rule.
# ---------------------------------------------------------------------------

def fetch_page(url: str, cache_filename: str) -> tuple[str, bool]:
    """
    Returns (html, was_cached). Raises FetchFailure if the page could not
    be retrieved.

    Retry rule: a timeout or a 5xx server error is retried once, after a
    short wait -- the server might just be having a bad moment. A 404
    (page doesn't exist) or 403 (site said no) is NOT retried -- asking
    again won't create a missing page, and hammering a page that said "no"
    is how a polite robot becomes a pest.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, cache_filename)

    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            html = f.read()
        print(f"CACHE HIT  {cache_filename}  ({len(html)} bytes)")
        return html, True

    headers = {"User-Agent": USER_AGENT}
    attempts = 0
    max_attempts = 2

    while attempts < max_attempts:
        attempts += 1
        try:
            response = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
        except requests.exceptions.Timeout:
            if attempts < max_attempts:
                print(f"RETRY      {cache_filename}  (timeout, attempt {attempts})")
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            raise FetchFailure(url, "timeout after retry")
        except requests.exceptions.RequestException as e:
            raise FetchFailure(url, f"request error: {e}")

        if response.status_code == 200:
            html = response.text
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"FETCH      {cache_filename}  ({len(html)} bytes)  status=200")
            time.sleep(DELAY_SECONDS)
            return html, False

        if response.status_code in (404, 403):
            # Do not retry -- asking again won't help either of these.
            raise FetchFailure(url, f"status {response.status_code}, not retrying")

        if 500 <= response.status_code < 600:
            if attempts < max_attempts:
                print(f"RETRY      {cache_filename}  (status {response.status_code}, attempt {attempts})")
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            raise FetchFailure(url, f"status {response.status_code} after retry")

        # Any other unexpected status -- treat as a non-retryable failure.
        raise FetchFailure(url, f"unexpected status {response.status_code}")

    raise FetchFailure(url, "exhausted retries")


# ---------------------------------------------------------------------------
# Discovery
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
        html, _ = fetch_page(current_url, cache_filename)
        for link in get_book_links(html, current_url):
            all_pairs.append((link, current_url))
        current_url = get_next_page_url(html, current_url)
        page_number += 1

    seen = {}
    for link, source in all_pairs:
        if link not in seen:
            seen[link] = source
    pairs = list(seen.items())

    if INJECT_FAKE_URL_FOR_TESTING:
        fake_url = "https://books.toscrape.com/catalogue/this-book-does-not-exist_9999/index.html"
        pairs.append((fake_url, BASE_CATALOGUE_URL))
        print(f"[testing] injected fake URL: {fake_url}")

    return pairs


def cache_filename_for_book(product_url: str) -> str:
    parts = product_url.rstrip("/").split("/")
    slug = parts[-2] if len(parts) >= 2 else parts[-1]
    return f"book-{slug}.html"


# ---------------------------------------------------------------------------
# Raw extraction
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
# Normalize
# ---------------------------------------------------------------------------

def parse_price_gbp(price_text: str | None) -> float | None:
    if not price_text:
        return None
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
    return {
        **raw,
        "price_gbp": parse_price_gbp(raw.get("price_text")),
        "rating_number": parse_rating_number(raw.get("rating_text")),
    }


def main():
    run_started_at = datetime.now(timezone.utc)

    cache_hits = 0
    pages_fetched = 0
    failed_pages = []

    def fetch_and_count(url, cache_filename):
        nonlocal cache_hits, pages_fetched
        html, was_cached = fetch_page(url, cache_filename)
        if was_cached:
            cache_hits += 1
        else:
            pages_fetched += 1
        return html

    # --- Discovery, with per-page failure isolation -----------------------
    all_pairs = []
    current_url = BASE_CATALOGUE_URL
    page_number = 1

    while current_url and page_number <= MAX_CATALOGUE_PAGES:
        cache_filename = f"catalogue-page-{page_number}.html"
        try:
            html = fetch_and_count(current_url, cache_filename)
        except FetchFailure as e:
            print(f"FAILED     {cache_filename}  ({e.reason})")
            failed_pages.append({"url": e.url, "reason": e.reason})
            break  # a broken catalogue page means we can't find "next" either
        for link in get_book_links(html, current_url):
            all_pairs.append((link, current_url))
        current_url = get_next_page_url(html, current_url)
        page_number += 1

    seen = {}
    for link, source in all_pairs:
        if link not in seen:
            seen[link] = source
    link_pairs = list(seen.items())

    if INJECT_FAKE_URL_FOR_TESTING:
        fake_url = "https://books.toscrape.com/catalogue/this-book-does-not-exist_9999/index.html"
        link_pairs.append((fake_url, BASE_CATALOGUE_URL))
        print(f"[testing] injected fake URL: {fake_url}")

    print(f"catalogue_pages={min(MAX_CATALOGUE_PAGES, 3)}")
    print(f"discovered={len(link_pairs)}")
    print(f"unique_urls={len(set(u for u, _ in link_pairs))}")

    # --- Detail pages, each handled separately so one bad page never
    #     takes down the rest of the run --------------------------------
    valid_books = []
    invalid_records = []
    seen_canonical_urls = set()

    for product_url, source_page in link_pairs:
        if product_url in seen_canonical_urls:
            continue
        seen_canonical_urls.add(product_url)

        cache_filename = cache_filename_for_book(product_url)

        try:
            html = fetch_and_count(product_url, cache_filename)
        except FetchFailure as e:
            print(f"FAILED     {cache_filename}  ({e.reason})")
            failed_pages.append({"url": e.url, "reason": e.reason})
            continue  # skip this one book, keep going with the rest

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

    # --- Store --------------------------------------------------------
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(os.path.join(OUTPUT_DIR, "books.json"), "w", encoding="utf-8") as f:
        json.dump(valid_books, f, indent=2, ensure_ascii=False)

    with open(os.path.join(OUTPUT_DIR, "errors.json"), "w", encoding="utf-8") as f:
        json.dump(invalid_records, f, indent=2, ensure_ascii=False)

    # --- Report ---------------------------------------------------------
    run_finished_at = datetime.now(timezone.utc)
    duration_seconds = (run_finished_at - run_started_at).total_seconds()

    report = {
        "started_at": run_started_at.isoformat(),
        "finished_at": run_finished_at.isoformat(),
        "duration_seconds": round(duration_seconds, 2),
        "pages_fetched": pages_fetched,
        "cache_hits": cache_hits,
        "valid_records": len(valid_books),
        "invalid_records": len(invalid_records),
        "failed_pages": len(failed_pages),
        "failed_page_details": failed_pages,
    }

    with open(os.path.join(OUTPUT_DIR, "run-report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"detail_pages={len(link_pairs)}")
    print(f"valid_records={len(valid_books)}")
    print(f"invalid_records={len(invalid_records)}")
    print(f"failed_pages={len(failed_pages)}")
    print(f"duration_seconds={report['duration_seconds']}")


if __name__ == "__main__":
    main()