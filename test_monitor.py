from dataclasses import dataclass

import pytest

from monitor import find_keywords, load_config, make_match, read_seen


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


def test_load_config_cleans_subreddit_prefix_and_blank_values(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"subreddits":["r/python",""],"keywords":[" help ",""],"limit_per_subreddit":25}')
    config = load_config(path)
    assert config["subreddits"] == ["python"]
    assert config["keywords"] == ["help"]


def test_load_config_rejects_an_excessive_limit(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"subreddits":["python"],"keywords":["help"],"limit_per_subreddit":500}')
    with pytest.raises(ValueError, match="between 1 and 100"):
        load_config(path)


def test_read_seen_rejects_non_list_state(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"unexpected": true}')
    with pytest.raises(ValueError, match="JSON list"):
        read_seen(path)

