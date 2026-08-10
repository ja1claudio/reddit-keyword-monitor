from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import praw
from dotenv import load_dotenv


LOG = logging.getLogger("reddit_monitor")


@dataclass(frozen=True)
class Match:
    date: str
    subreddit: str
    title: str
    snippet: str
    matched_keywords: str
    url: str
    post_id: str


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        config = json.load(handle)
    required = {"subreddits", "keywords"}
    missing = required.difference(config)
    if missing:
        raise ValueError(f"Missing configuration keys: {', '.join(sorted(missing))}")
    if not config["subreddits"] or not config["keywords"]:
        raise ValueError("At least one subreddit and one keyword are required")
    return config


def find_keywords(text: str, keywords: Iterable[str]) -> list[str]:
    normalized = text.casefold()
    return [keyword for keyword in keywords if keyword.casefold() in normalized]


def make_match(post, keywords: Iterable[str]) -> Match | None:
    body = getattr(post, "selftext", "") or ""
    combined = f"{post.title}\n{body}"
    found = find_keywords(combined, keywords)
    if not found:
        return None
    created = datetime.fromtimestamp(post.created_utc, tz=timezone.utc).isoformat()
    snippet = " ".join(body.split())[:280]
    return Match(
        date=created,
        subreddit=str(post.subreddit),
        title=post.title,
        snippet=snippet,
        matched_keywords=", ".join(found),
        url=f"https://www.reddit.com{post.permalink}",
        post_id=post.id,
    )


def read_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")))


def write_seen(path: Path, seen: set[str]) -> None:
    path.write_text(json.dumps(sorted(seen), indent=2), encoding="utf-8")


def append_csv(path: Path, matches: list[Match]) -> None:
    if not matches:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(matches[0])))
        if not exists:
            writer.writeheader()
        writer.writerows(asdict(match) for match in matches)


def append_google_sheet(matches: list[Match]) -> None:
    if not matches:
        return
    import gspread

    credentials = os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"]
    sheet_id = os.environ["GOOGLE_SHEET_ID"]
    worksheet_name = os.getenv("GOOGLE_WORKSHEET", "Matches")
    worksheet = gspread.service_account(filename=credentials).open_by_key(sheet_id).worksheet(worksheet_name)
    rows = [list(asdict(match).values()) for match in matches]
    worksheet.append_rows(rows, value_input_option="RAW")


def collect_once(reddit, config: dict, seen: set[str]) -> list[Match]:
    matches: list[Match] = []
    limit = int(config.get("limit_per_subreddit", 50))
    for name in config["subreddits"]:
        LOG.info("Checking r/%s", name)
        for post in reddit.subreddit(name).new(limit=limit):
            if post.id in seen:
                continue
            seen.add(post.id)
            match = make_match(post, config["keywords"])
            if match:
                matches.append(match)
    return matches


def build_reddit_client():
    required = ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Missing environment variables: {', '.join(missing)}")
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ["REDDIT_USER_AGENT"],
        check_for_async=False,
    )


def run(config_path: Path, interval: int, once: bool, dry_run: bool) -> None:
    load_dotenv()
    config = load_config(config_path)
    reddit = build_reddit_client()
    state_path = Path(config.get("state_path", "state.json"))
    seen = read_seen(state_path)
    while True:
        matches = collect_once(reddit, config, seen)
        LOG.info("Found %d new matches", len(matches))
        if dry_run:
            for match in matches:
                print(json.dumps(asdict(match), ensure_ascii=False))
        elif config.get("output", "csv") == "google_sheets":
            append_google_sheet(matches)
            write_seen(state_path, seen)
        else:
            append_csv(Path(config.get("csv_path", "output/reddit_matches.csv")), matches)
            write_seen(state_path, seen)
        if once:
            return
        time.sleep(interval)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor Reddit posts for keyword matches")
    parser.add_argument("--config", type=Path, default=Path("config.example.json"))
    parser.add_argument("--interval", type=int, default=900, help="Seconds between scans")
    parser.add_argument("--once", action="store_true", help="Run one scan and exit")
    parser.add_argument("--dry-run", action="store_true", help="Print matches without writing output")
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    run(args.config, args.interval, args.once, args.dry_run)

