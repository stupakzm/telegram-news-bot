"""Tests for delivery/ratelimit.py — the shared token bucket (DEL-01)."""
import threading
import time

from delivery.ratelimit import TokenBucket


def test_burst_then_throttles_to_rate():
    # rate 10/s, burst 1 -> first acquire immediate, next 4 pace at ~0.1s each
    bucket = TokenBucket(rate_per_sec=10, burst=1)
    start = time.monotonic()
    for _ in range(5):
        bucket.acquire()
    elapsed = time.monotonic() - start
    # 4 refills at 0.1s = ~0.4s; allow generous slack, but it must have blocked
    assert elapsed >= 0.35


def test_initial_burst_is_not_throttled():
    # a full burst of tokens should be handed out with negligible delay
    bucket = TokenBucket(rate_per_sec=5, burst=10)
    start = time.monotonic()
    for _ in range(10):
        bucket.acquire()
    assert (time.monotonic() - start) < 0.2


def test_concurrent_acquire_respects_global_rate():
    # 12 threads all acquire from one bucket at 20/s, burst 2.
    # Aggregate must be paced: >= (12 - 2) / 20 = 0.5s of throttling.
    bucket = TokenBucket(rate_per_sec=20, burst=2)
    n = 12
    barrier = threading.Barrier(n)
    done_order = []
    lock = threading.Lock()

    def worker():
        barrier.wait()
        bucket.acquire()
        with lock:
            done_order.append(time.monotonic())

    start = time.monotonic()
    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert len(done_order) == n  # everyone got through, no deadlock
    assert (max(done_order) - start) >= 0.45


def test_available_refills_over_time():
    bucket = TokenBucket(rate_per_sec=100, burst=5)
    for _ in range(5):
        bucket.acquire()
    assert bucket.available() < 1
    time.sleep(0.1)  # ~10 tokens would refill, capped at burst=5
    assert bucket.available() > 1
