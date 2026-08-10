# Reddit Keyword Monitor

A small, production-minded Python automation that monitors selected subreddits,
matches configurable keywords, and exports new discussions to CSV or Google
Sheets.

## Features

- Uses the official Reddit API through PRAW.
- Case-insensitive keyword and phrase matching.
- Avoids duplicate records with a local state file.
- Exports to CSV without any cloud credentials.
- Optionally appends rows to Google Sheets.
- Includes structured logging, tests, and a dry-run mode.

## Setup

1. Install Python 3.11+ and run `pip install -r requirements.txt`.
2. Copy `.env.example` to `.env` and add your Reddit API credentials.
3. Run `python monitor.py --config config.example.json --once`.

For Google Sheets, create a service account, share the target sheet with its
email address, and set `GOOGLE_SERVICE_ACCOUNT_FILE` and
`GOOGLE_SHEET_ID` in `.env`.

## Configuration

Edit `config.example.json` to select subreddits, keywords, output mode, and the
number of recent posts inspected per community.

```json
{
  "subreddits": ["marketing", "smallbusiness"],
  "keywords": ["not converting", "struggling", "confused"],
  "limit_per_subreddit": 50,
  "output": "csv",
  "csv_path": "output/reddit_matches.csv"
}
```

Run continuously with `python monitor.py --config config.example.json --interval 900`.

## Responsible use

This project uses Reddit's official API and should be configured within its
rate limits and terms. It does not bypass authentication, CAPTCHAs, or access
controls.

