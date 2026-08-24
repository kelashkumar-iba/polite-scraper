## Target classification

**Site:** [Books to Scrape](https://books.toscrape.com) — a sandbox
site built specifically for practicing web scraping.

**Why this is appropriate:** The site states directly on its homepage,
"We love being scraped!" and describes itself as "a demo website for
web scraping purposes." Prices and ratings are explicitly randomly
generated and carry no real meaning. This is not a live business —
it exists for exactly this purpose.

**robots.txt result:** Requested `https://books.toscrape.com/robots.txt`
on [today's date] — the server returned a 404 (no robots.txt file
exists at that path). A missing file is not the same as permission;
it simply means there are no automated crawling rules published for
this site. Given the site's own explicit invitation to scrape it, this
absence isn't a red flag here — but it also isn't the reason scraping
is okay. The reason is the "we love being scraped" statement itself.

**Scope:** Only the first 3 catalogue pages
(`catalogue/page-1.html` through `page-3.html`), and the individual
book detail pages linked from those 3 pages — 60 books total, out of
the site's full 1000-book, 50-page catalogue.

**Data collected:** For each book — title, price, availability text,
star rating, description, and its own page URL. No personal data,
no login-gated content, nothing beyond product listings the site
already displays publicly to any visitor.

I will not reuse this code on another site without checking its rules
and terms first.