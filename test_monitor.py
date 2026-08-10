from dataclasses import dataclass

import pytest

from monitor import find_keywords, make_match


@dataclass
class FakePost:
    id: str = "abc123"
    title: str = "My landing page is not converting"
    selftext: str = "I am confused about the next step."
    subreddit: str = "marketing"
    created_utc: float = 1_700_000_000
    permalink: str = "/r/marketing/comments/abc123/example/"


def test_find_keywords_is_case_insensitive():
    assert find_keywords("I am STRUGGLING today", ["struggling", "easy"]) == ["struggling"]


def test_make_match_contains_all_expected_fields():
    match = make_match(FakePost(), ["not converting", "confused"])
    assert match is not None
    assert match.post_id == "abc123"
    assert match.matched_keywords == "not converting, confused"
    assert match.url.startswith("https://www.reddit.com/")


def test_make_match_returns_none_without_keywords():
    assert make_match(FakePost(), ["unrelated phrase"]) is None

