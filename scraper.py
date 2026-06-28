import argparse
import csv
import re
import sys
import time
import urllib.robotparser
from datetime import datetime
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://news.ycombinator.com"
JOBS_URL = f"{BASE_URL}/jobs"
REQUEST_DELAY_SECONDS = 2

DEFAULT_KEYWORDS = ["data", "python", "ml", "machine learning", "analyst"]


def check_robots_permission(base_url: str, path: str) -> bool:
    robots_url = urljoin(base_url, "/robots.txt")
    try:
        response = requests.get(robots_url, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        print(f"  Warning: could not fetch robots.txt ({exc}).")
        return False

    rp = urllib.robotparser.RobotFileParser()
    rp.parse(response.text.splitlines())
    return rp.can_fetch("*", urljoin(base_url, path))


def fetch_page(url: str) -> str | None:
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.exceptions.Timeout:
        print(f"  Error: request to {url} timed out.")
    except requests.exceptions.HTTPError as exc:
        print(f"  Error: server returned {exc.response.status_code} for {url}. "
              f"Skipping this page.")
    except requests.exceptions.ConnectionError:
        print(f"  Error: could not connect to {url} — check your internet "
              f"connection. Skipping this page.")
    except requests.exceptions.RequestException as exc:
        print(f"  Error: unexpected request failure for {url} ({exc}). "
              f"Skipping this page.")
    return None


def extract_location_from_title(title: str) -> str:
    bracket_match = re.search(r"\[([^\]]+)\]\s*$", title)
    if bracket_match:
        return bracket_match.group(1).strip()

    paren_match = re.search(r"\(([^)]*(?:remote|onsite|on-site|hybrid|"
                             r"nyc|sf|berlin|london|india)[^)]*)\)\s*$",
                             title, re.IGNORECASE)
    if paren_match:
        return paren_match.group(1).strip()

    remote_match = re.search(r"\b(remote|onsite|on-site|hybrid)\b",
                              title, re.IGNORECASE)
    if remote_match:
        return remote_match.group(1).title()

    return "Not specified"


def extract_company_from_title(title: str) -> str:
    yc_match = re.match(r"^(.*?)\s*\(YC\s", title)
    if yc_match:
        return yc_match.group(1).strip()

    hiring_match = re.match(r"^(.*?)\s+(?:is|are)\s+hiring", title, re.IGNORECASE)
    if hiring_match:
        return hiring_match.group(1).strip()

    return "Not specified"


def parse_jobs_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    rows = soup.find_all("tr", class_="athing")
    if not rows:
        print("  Warning: no job rows found on this page — "
              "page layout may have changed or page is empty.")
        return jobs

    for row in rows:
        try:
            title_cell = row.find("span", class_="titleline")
            if title_cell is None or title_cell.find("a") is None:
                continue

            link_tag = title_cell.find("a")
            title = link_tag.get_text(strip=True)
            link = link_tag.get("href", "Not specified")
            if link and not link.startswith("http"):
                link = urljoin(BASE_URL, link)
 
            subtext_row = row.find_next_sibling("tr")
            date_posted = "Not specified"
            if subtext_row is not None:
                age_tag = subtext_row.find("span", class_="age")
                if age_tag is not None:
                    age_link = age_tag.find("a")
                    date_posted = (age_link.get_text(strip=True)
                                    if age_link else age_tag.get_text(strip=True))

            jobs.append({
                "title": title,
                "company": extract_company_from_title(title),
                "location": extract_location_from_title(title),
                "link": link,
                "date_posted": date_posted,
            })
        except Exception as exc:
            print(f"  Warning: skipped a malformed listing ({exc}).")
            continue

    return jobs


def get_next_page_url(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    more_link = soup.find("a", string="More")
    if more_link and more_link.get("href"):
        return urljoin(BASE_URL, more_link["href"])
    return None


def matches_keyword(job: dict, keywords: list[str]) -> bool:
    title_lower = job["title"].lower()
    return any(kw.lower() in title_lower for kw in keywords)


def scrape_jobs(keywords: list[str], max_pages: int) -> list[dict]:
    print("Checking robots.txt permission...")
    allowed = check_robots_permission(BASE_URL, "/jobs")
    if not allowed:
        print("Stopping: either robots.txt disallows scraping this path, "
              "or its rules could not be confirmed (see warning above)")
        sys.exit(1)
    print("  robots.txt allows scraping /jobs. Proceeding politely.\n")

    all_jobs = []
    url = JOBS_URL
    page_num = 1

    while url and page_num <= max_pages:
        print(f"Scanning page {page_num} ({url})...")
        html = fetch_page(url)

        if html is None:
            print(f"  Could not fetch page {page_num}. Stopping pagination here.")
            break

        page_jobs = parse_jobs_page(html)
        print(f"  Found {len(page_jobs)} listings on this page.")

        matched = [j for j in page_jobs if matches_keyword(j, keywords)]
        print(f"  {len(matched)} matched keyword filter {keywords}.")
        all_jobs.extend(matched)

        next_url = get_next_page_url(html)
        if next_url is None:
            print("  No further pages found.")
            break

        url = next_url
        page_num += 1

        if url and page_num <= max_pages:
            time.sleep(REQUEST_DELAY_SECONDS)

    return all_jobs


def export_to_csv(jobs: list[dict], output_path: str) -> None:
    fieldnames = ["title", "company", "location", "link", "date_posted"]

    try:
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for job in jobs:
                writer.writerow(job)
    except OSError as exc:
        print(f"Error: could not write to {output_path} ({exc}). "
              f"Check the path and your write permissions.")
        sys.exit(1)

    print(f"\nSaved {len(jobs)} matching listings to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Hacker News 'Who is Hiring' jobs, filtered by keyword."
    )
    parser.add_argument(
        "--keyword", action="append", dest="keywords",
        help="Keyword to filter by (case-insensitive, matched in title). "
             "Can be passed multiple times. Default: data/python/ml/analyst.",
    )
    parser.add_argument(
        "--pages", type=int, default=2,
        help="Maximum number of listing pages to scan (default: 2).",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output CSV filename (default: auto-generated with timestamp).",
    )
    args = parser.parse_args()

    keywords = args.keywords if args.keywords else DEFAULT_KEYWORDS

    if args.output:
        output_path = args.output
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"internships_{timestamp}.csv"

    print("Data/Tech Internship Scraper — Hacker News Jobs Board")
    print(f"Keywords: {keywords}")
    print(f"Max pages: {args.pages}")
    print(f"Output file: {output_path}\n")

    jobs = scrape_jobs(keywords, args.pages)

    if not jobs:
        print("\nNo matching listings found. Try different keywords.")

    export_to_csv(jobs, output_path)

    print("Done.")


if __name__ == "__main__":
    main()