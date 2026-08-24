import os
import requests

# --- Politeness settings -----------------------------------------------
# A polite scraper always identifies itself honestly, gives up instead of
# waiting forever, and reads from a local cache during development so the
# real site is only ever asked once per page.

USER_AGENT = "FlyRankInternshipA9/1.0 (+https://github.com/kelashkumar-iba/polite-scraper)"
TIMEOUT_SECONDS = 10
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "cache")


def fetch_page(url: str, cache_filename: str) -> str:
    """
    Fetches a page politely, or reads it from the local cache if we've
    already fetched it before. Returns the raw HTML as a string.

    Raises an exception if the real request fails or doesn't return 200 --
    callers are expected to handle that (this stage doesn't handle failure
    yet, that's Stage 5).
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, cache_filename)

    # 1. If we've already saved this page, read the saved copy instead of
    #    asking the site again.
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            html = f.read()
        print(f"CACHE HIT  {cache_filename}  ({len(html)} bytes)")
        return html

    # 2. Otherwise, make a real, polite request.
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)

    # 3. Only a 200 means "here is your page." Anything else is a failed
    #    fetch, not HTML to parse -- raise so the caller knows it failed.
    response.raise_for_status()

    html = response.text

    # 4. Save it to cache so every future run (and every restart while
    #    developing) reads the saved copy instead of hitting the site again.
    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"FETCH      {cache_filename}  ({len(html)} bytes)  status={response.status_code}")
    return html


def main():
    url = "https://books.toscrape.com/catalogue/page-1.html"
    fetch_page(url, "catalogue-page-1.html")


if __name__ == "__main__":
    main()