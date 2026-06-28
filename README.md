# Data/Tech Internship & Job Scraper

Scrapes the website (https://news.ycombinator.com/jobs) for job
board, filters listings by keyword, and exports matches to a CSV with:
`title, company, location, link, date_posted`.


## Installation

git clone <this-repo>
cd internship-scraper
pip install -r requirements.txt
Requires Python 3.10+


## What it does

1. Checks `robots.txt` for the target site at runtime — refuses to run if
   scraping isn't permitted, or if `robots.txt` can't be confirmed at all
   (e.g. no internet connection).
2. Fetches the jobs listing page with a descriptive header.
3. Parses each listing row, extracting title, a best-guess company name,
   a best-guess location (HN doesn't have a structured location field —
   it's sometimes embedded in the title in brackets),the posting link, 
   and how long ago it was posted.
4. Filters listings against your keyword list.
5. Writes everything to CSV — including writing a header-only CSV if
   nothing matched, so downstream tools don't break on a missing file.