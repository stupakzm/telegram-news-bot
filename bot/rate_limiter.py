"""Per-user command rate limiting with sliding window, backed by Turso DB."""
import time
from math import ceil
import db.client as db

MAX_COMMANDS = 5
WINDOW_SECONDS = 60


def check_rate_limit(user_id: int) -> tuple[bool, int]:
    """Check if user is rate-limited. Persisted in DB so it works on serverless.

    Returns (allowed, retry_after_seconds).
    allowed=True means the command can proceed.
    retry_after_seconds is 0 when allowed, otherwise seconds until oldest command expires.
    """
    now = time.time()
    cutoff = int(now - WINDOW_SECONDS)

    # Count recent commands in the window
    rows = db.execute(
        "SELECT occurred_at FROM rate_limit_log WHERE user_id = ? AND occurred_at > ? ORDER BY occurred_at ASC",
        [user_id, cutoff],
    )

    if len(rows) >= MAX_COMMANDS:
        oldest = rows[0]["occurred_at"]
        retry_after = ceil(WINDOW_SECONDS - (now - oldest))
        return False, max(retry_after, 1)

    # Record this command
    db.execute_many([(
        "INSERT INTO rate_limit_log (user_id, occurred_at) VALUES (?, ?)",
        [user_id, int(now)],
    )])

    # Prune old entries (keep table small)
    db.execute_many([(
        "DELETE FROM rate_limit_log WHERE user_id = ? AND occurred_at <= ?",
        [user_id, int(cutoff)],
    )])

    return True, 0
