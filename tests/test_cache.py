import pytest
from unittest.mock import patch
import os
from datetime import datetime, timezone

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")


def test_current_quarter_maps_hours_correctly():
    from delivery.cache import current_quarter
    assert current_quarter(0) == 0
    assert current_quarter(5) == 0
    assert current_quarter(6) == 1
    assert current_quarter(11) == 1
    assert current_quarter(12) == 2
    assert current_quarter(17) == 2
    assert current_quarter(18) == 3
    assert current_quarter(23) == 3


@patch("delivery.cache.db.execute")
def test_get_cached_returns_articles_on_hit(mock_execute):
    import json
    cached = [{"title": "Test", "url": "https://x.com"}]
    mock_execute.return_value = [{"articles": json.dumps(cached)}]

    from delivery.cache import get_cached
    result = get_cached("default", 1, "2026-03-14", 2)
    assert result == cached


@patch("delivery.cache.db.execute")
def test_get_cached_returns_none_on_miss(mock_execute):
    mock_execute.return_value = []

    from delivery.cache import get_cached
    result = get_cached("default", 1, "2026-03-14", 2)
    assert result is None


@patch("delivery.cache.db.execute_many")
def test_set_cache_writes_correct_row(mock_execute_many):
    import json
    from delivery.cache import set_cache
    articles = [{"title": "News", "url": "https://example.com"}]
    set_cache("custom", 42, "2026-03-14", 1, articles)

    call_args = mock_execute_many.call_args[0][0]
    sql, args = call_args[0]
    assert "INSERT OR REPLACE" in sql
    assert args[0] == "custom"
    assert args[1] == 42
    assert args[2] == "2026-03-14"
    assert args[3] == 1
    assert json.loads(args[4]) == articles
