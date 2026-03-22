"""Per-user command rate limiting with sliding window."""
import time
from collections import deque
from math import ceil

_user_timestamps: dict[int, deque] = {}
MAX_COMMANDS = 5
WINDOW_SECONDS = 60


def check_rate_limit(user_id: int) -> tuple[bool, int]:
    """Check if user is rate-limited.

    Returns (allowed, retry_after_seconds).
    allowed=True means the command can proceed.
    retry_after_seconds is 0 when allowed, otherwise seconds until oldest command expires.
    """
    now = time.time()
    timestamps = _user_timestamps.setdefault(user_id, deque())

    # Evict expired entries
    while timestamps and timestamps[0] < now - WINDOW_SECONDS:
        timestamps.popleft()

    if len(timestamps) >= MAX_COMMANDS:
        retry_after = ceil(WINDOW_SECONDS - (now - timestamps[0]))
        return False, max(retry_after, 1)

    timestamps.append(now)
    return True, 0
