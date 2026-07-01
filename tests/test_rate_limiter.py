from math import ceil
from unittest.mock import patch


class _FakeDB:
    """In-memory stand-in for db.client wired to rate_limit_log semantics."""

    def __init__(self):
        self.rows: list[dict] = []

    def execute(self, sql: str, args: list):
        assert "SELECT occurred_at FROM rate_limit_log" in sql
        user_id, cutoff = args
        return [
            {"occurred_at": r["occurred_at"]}
            for r in self.rows
            if r["user_id"] == user_id and r["occurred_at"] > cutoff
        ]

    def execute_many(self, statements: list):
        for sql, args in statements:
            if sql.startswith("INSERT INTO rate_limit_log"):
                user_id, occurred_at = args
                self.rows.append({"user_id": user_id, "occurred_at": occurred_at})
            elif sql.startswith("DELETE FROM rate_limit_log"):
                user_id, cutoff = args
                self.rows = [
                    r for r in self.rows
                    if not (r["user_id"] == user_id and r["occurred_at"] <= cutoff)
                ]
            else:
                raise AssertionError(f"unexpected sql: {sql!r}")


def _patch_db(fake: _FakeDB):
    return patch.multiple(
        "bot.rate_limiter.db",
        execute=fake.execute,
        execute_many=fake.execute_many,
    )


def test_allows_up_to_max_commands():
    from bot.rate_limiter import check_rate_limit
    fake = _FakeDB()
    with _patch_db(fake):
        for i in range(5):
            allowed, retry = check_rate_limit(user_id=100)
            assert allowed is True, f"Command {i+1} should be allowed"
            assert retry == 0


def test_blocks_after_max_commands():
    from bot.rate_limiter import check_rate_limit
    fake = _FakeDB()
    with _patch_db(fake):
        for _ in range(5):
            check_rate_limit(user_id=100)
        allowed, retry = check_rate_limit(user_id=100)
        assert allowed is False
        assert retry > 0
        assert retry <= 60


@patch("bot.rate_limiter.time")
def test_allows_after_window_expires(mock_time):
    from bot.rate_limiter import check_rate_limit
    fake = _FakeDB()
    with _patch_db(fake):
        mock_time.time.return_value = 1000.0
        for _ in range(5):
            check_rate_limit(user_id=100)
        allowed, _ = check_rate_limit(user_id=100)
        assert allowed is False
        mock_time.time.return_value = 1061.0
        allowed, retry = check_rate_limit(user_id=100)
        assert allowed is True
        assert retry == 0


def test_independent_user_limits():
    from bot.rate_limiter import check_rate_limit
    fake = _FakeDB()
    with _patch_db(fake):
        for _ in range(5):
            check_rate_limit(user_id=100)
        allowed_a, _ = check_rate_limit(user_id=100)
        assert allowed_a is False
        allowed_b, retry_b = check_rate_limit(user_id=200)
        assert allowed_b is True
        assert retry_b == 0


@patch("bot.rate_limiter.time")
def test_retry_after_value(mock_time):
    from bot.rate_limiter import check_rate_limit
    fake = _FakeDB()
    with _patch_db(fake):
        mock_time.time.return_value = 1000.0
        for _ in range(5):
            check_rate_limit(user_id=100)
        mock_time.time.return_value = 1030.0
        allowed, retry = check_rate_limit(user_id=100)
        assert allowed is False
        # Oldest was recorded at int(1000)=1000; retry = ceil(60 - (1030 - 1000)) = 30
        assert retry == ceil(30)
