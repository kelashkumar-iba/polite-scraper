# Polite Scraper

A small, polite scraping pipeline that downloads the first 3 catalogue
pages of [Books to Scrape](https://books.toscrape.com), visits all 60
book detail pages, and turns the messy HTML into clean, schema-checked
JSON -- without hammering the server, and without crashing on a broken
page.

## Target classification

**Site:** [Books to Scrape](https://books.toscrape.com) -- a sandbox
site built specifically for practicing web scraping.

**Why this is appropriate:** The site states directly on its homepage,
"We love being scraped!" and describes itself as "a demo website for
web scraping purposes." Prices and ratings are explicitly randomly
generated and carry no real meaning. This is not a live business --
it exists for exactly this purpose.

**robots.txt result:** Requested `https://books.toscrape.com/robots.txt`
-- the server returned a 404 (no robots.txt file exists at that path).
A missing file is not the same as permission; it simply means there
are no automated crawling rules published for this site. Given the
site's own explicit invitation to scrape it, this absence isn't a red
flag here -- but it also isn't the reason scraping is okay. The reason
is the "we love being scraped" statement itself.

**Scope:** Only the first 3 catalogue pages
(`catalogue/page-1.html` through `page-3.html`), and the 60 individual
book detail pages linked from those 3 pages.

**Data collected:** For each book -- title, price, availability text,
star rating, description, and its own page URL. No personal data,
no login-gated content, nothing beyond product listings the site
already displays publicly to any visitor.

I will not reuse this code on another site without checking its
rules and terms first.

## Why this assignment needed no browser

The book title, price, availability, rating, and description are all
present in the raw HTML the server sends back on the very first
request -- nothing here is injected by JavaScript after the page
loads. A plain HTTP GET with `requests` sees exactly the same content
a browser would render. Running this through a real browser (e.g.
Playwright) would only add startup cost, memory use, and complexity,
with no extra data gained.

## Politeness rules this scraper follows

- **User-agent**: every request identifies itself as
  `FlyRankInternshipA9/1.0 (+link to this repo)` -- never a spoofed
  browser string.
- **Timeout**: every request gives up after 10 seconds rather than
  hanging forever.
- **Delay**: at least 0.5 seconds between real requests to the site.
  Cached pages need no delay, since they never leave the local machine.
- **Status check**: only a `200` is treated as a real page. Anything
  else is a failed fetch, not HTML to parse.
- **Cache**: every page is saved to `cache/` on first fetch. All
  later runs during development read from the cache instead of
  re-asking the site.
- **Retry rules**: a timeout or a `5xx` server error is retried once
  after a short wait. A `404` or `403` is never retried -- asking
  again won't create a missing page, and repeating a request the site
  said no to is how a polite robot becomes a pest.

## Record schema

Each validated record in `output/books.json` has this shape (checked
with Pydantic before it's ever written):

```json
{
  "title": "A Light in the Attic",
  "product_url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
  "price_text": "£51.77",
  "price_gbp": 51.77,
  "availability_text": "In stock (22 available)",
  "rating_text": "Three",
  "rating_number": 3,
  "description": "...",
  "source_page": "https://books.toscrape.com/catalogue/page-1.html",
  "fetched_at": "2026-08-16T10:00:00+00:00"
}
```

Raw text fields (`price_text`, `rating_text`) are kept alongside their
clean, typed equivalents (`price_gbp`, `rating_number`) -- nothing is
thrown away, both live side by side. `description` is the only field
allowed to be `null`, since some books genuinely have none. Records
that fail validation are written to `output/errors.json` with the
reason, and never reach `books.json`.

## Idempotency

`product_url` is each record's canonical identity. Running the
scraper twice produces the same 60 records, not 120 -- the script
de-duplicates by URL before writing, and a rerun mostly reads from
the cache rather than re-fetching.

## Running it

```bash
git clone https://github.com/kelashkumar-iba/polite-scraper.git
cd polite-scraper
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows PowerShell
pip install -r requirements.txt
python src/main.py
```

First run fetches and caches all 63 pages (3 catalogue + 60 book
pages), politely spaced 0.5s apart -- expect it to take 30-40 seconds.
Every run after that reads from the cache and finishes in a couple of
seconds.

Output:
- `output/books.json` -- 60 validated records
- `output/errors.json` -- any records that failed validation (empty on
  a clean run)
- `output/run-report.json` -- honest numbers about what the run did

## Sample run report

```json
{
  "started_at": "2026-08-16T10:00:00.000000+00:00",
  "finished_at": "2026-08-16T10:00:35.120000+00:00",
  "duration_seconds": 35.12,
  "pages_fetched": 0,
  "cache_hits": 63,
  "valid_records": 60,
  "invalid_records": 0,
  "failed_pages": 0,
  "failed_page_details": []
}
```

*(Replace this with your own actual run-report.json contents.)*

## Proving failure survival

`src/main.py` has an `INJECT_FAKE_URL_FOR_TESTING` flag near the top.
Setting it to `True` adds one deliberately broken, made-up book URL to
the list before fetching. On that run, the fake URL fails immediately
(a real 404, not retried, per the retry rules above) and is logged
into `failed_pages` -- but the other 60 real records are collected
and written normally. The run finishes instead of crashing.

## Ethics note

- Use an official API when one exists, instead of scraping.
- Never bypass logins, paywalls, CAPTCHAs, or explicit blocks.
- Collect only the data actually needed for the task.
- Identify the scraper honestly (a real user-agent, not a spoofed
  browser string), and go slowly enough that the target never
  notices unusual load.
- This scraper was built and tested against a public practice
  sandbox that explicitly invites scraping. None of these habits
  are optional even on a sandbox -- they're the muscle memory that
  matters the day the target is a real, live site.

## One honest limitation

This scraper handles one class of failure (a single broken page) by
skipping and logging it. It does not yet implement true exponential
backoff, does not respect a `Retry-After` header, and its retry logic
is a single fixed-delay retry rather than a real backoff schedule.
That's intentional for this stage -- the assignment's own next
iteration (A16) builds the production-grade version of exactly this.

## Technologies used

Python 3 · requests · BeautifulSoup4 · Pydantic

## Project structure

```
polite-scraper/
├── src/
│   └── main.py
├── cache/              (gitignored -- local only)
├── output/
│   ├── books.json
│   ├── errors.json
│   └── run-report.json
├── .gitignore
├── requirements.txt
└── README.md
```

## Assignment

FlyRank Internship -- Backend Track
Week 5: The Polite Scraper (BE-05)