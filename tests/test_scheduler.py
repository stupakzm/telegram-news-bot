import os
import time
from datetime import datetime, timezone
from unittest.mock import patch

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")


@patch("delivery.scheduler.db.execute_many")
@patch("delivery.scheduler.db.execute")
def test_get_due_users_matches_vip_local_hour(mock_exec, mock_exec_many):
    # UTC 17:00 → Europe/Kyiv (UTC+3 in summer DST) → 20:00, which is in VIP hours
    now = datetime(2026, 7, 15, 17, 0, tzinfo=timezone.utc)
    future = int(now.timestamp()) + 86400
    mock_exec.return_value = [
        {"user_id": 1, "tier": "vip", "tier_expires_at": future, "timezone": "Europe/Kyiv"}
    ]
    from delivery.scheduler import get_due_users
    due = get_due_users(now)
    assert len(due) == 1
    assert due[0]["user_id"] == 1


@patch("delivery.scheduler.db.execute_many")
@patch("delivery.scheduler.db.execute")
def test_get_due_users_skips_off_hour(mock_exec, mock_exec_many):
    # UTC 02:00 → Europe/Kyiv 05:00 — not in VIP hours (13, 20)
    now = datetime(2026, 7, 15, 2, 0, tzinfo=timezone.utc)
    future = int(now.timestamp()) + 86400
    mock_exec.return_value = [
        {"user_id": 1, "tier": "vip", "tier_expires_at": future, "timezone": "Europe/Kyiv"}
    ]
    from delivery.scheduler import get_due_users
    due = get_due_users(now)
    assert due == []


@patch("delivery.scheduler.db.execute_many")
@patch("delivery.scheduler.db.execute")
def test_get_due_users_expires_past_plan(mock_exec, mock_exec_many):
    now = datetime(2026, 7, 15, 13, 0, tzinfo=timezone.utc)
    past = int(now.timestamp()) - 86400
    mock_exec.return_value = [
        {"user_id": 5, "tier": "vip", "tier_expires_at": past, "timezone": "UTC"}
    ]
    from delivery.scheduler import get_due_users
    due = get_due_users(now)
    assert due == []
    # Auto-expire UPDATE was issued
    sql, args = mock_exec_many.call_args[0][0][0]
    assert "tier = 'expired'" in sql
    assert 5 in args


@patch("delivery.scheduler.db.execute_many")
@patch("delivery.scheduler.db.execute")
def test_svip_due_at_one_of_four_hours(mock_exec, mock_exec_many):
    # UTC 14:00, UTC tz → 14:00 local → in SVIP hours
    now = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)
    future = int(now.timestamp()) + 86400
    mock_exec.return_value = [
        {"user_id": 9, "tier": "svip", "tier_expires_at": future, "timezone": "UTC"}
    ]
    from delivery.scheduler import get_due_users
    due = get_due_users(now)
    assert len(due) == 1


@patch("delivery.scheduler.db.execute_many")
@patch("delivery.scheduler.db.execute")
def test_trial_uses_vip_hours(mock_exec, mock_exec_many):
    now = datetime(2026, 7, 15, 13, 0, tzinfo=timezone.utc)
    future = int(now.timestamp()) + 86400
    mock_exec.return_value = [
        {"user_id": 7, "tier": "trial", "tier_expires_at": future, "timezone": "UTC"}
    ]
    from delivery.scheduler import get_due_users
    due = get_due_users(now)
    assert len(due) == 1
    assert due[0]["tier"] == "trial"


def test_user_today_start_utc_ts_handles_offset_tz():
    # 2026-07-15 02:00 UTC = 2026-07-15 05:00 Kyiv
    # midnight in Kyiv = 2026-07-14 21:00 UTC
    from delivery.scheduler import user_today_start_utc_ts
    now = datetime(2026, 7, 15, 2, 0, tzinfo=timezone.utc)
    ts = user_today_start_utc_ts("Europe/Kyiv", now)
    midnight_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
    assert midnight_utc == datetime(2026, 7, 14, 21, 0, tzinfo=timezone.utc)


def test_user_today_start_utc_ts_defaults_to_utc():
    from delivery.scheduler import user_today_start_utc_ts
    now = datetime(2026, 7, 15, 14, 30, tzinfo=timezone.utc)
    ts = user_today_start_utc_ts(None, now)
    midnight_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
    assert midnight_utc == datetime(2026, 7, 15, 0, 0, tzinfo=timezone.utc)


def test_user_today_start_utc_ts_unknown_tz_falls_back_to_utc():
    from delivery.scheduler import user_today_start_utc_ts
    now = datetime(2026, 7, 15, 14, 30, tzinfo=timezone.utc)
    ts = user_today_start_utc_ts("Mars/Phobos", now)
    midnight_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
    assert midnight_utc == datetime(2026, 7, 15, 0, 0, tzinfo=timezone.utc)


def _ts(y, mo, d, h, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp())


def test_covered_slots_first_ever_run_covers_current_hour_only():
    from delivery.scheduler import covered_slots
    now = datetime(2026, 8, 6, 19, 0, tzinfo=timezone.utc)
    slots = covered_slots(now, None)
    assert [s.hour for s in slots] == [19]


def test_covered_slots_backfills_hours_missed_by_a_runner_outage():
    # Last success 16:00; the 17:00, 18:00 and 19:00 runs never got a runner.
    from delivery.scheduler import covered_slots
    now = datetime(2026, 8, 6, 20, 0, tzinfo=timezone.utc)
    slots = covered_slots(now, _ts(2026, 8, 6, 16))
    assert [s.hour for s in slots] == [17, 18, 19, 20]


def test_covered_slots_caps_backfill_at_max_catchup():
    from delivery.scheduler import covered_slots, MAX_CATCHUP_HOURS
    now = datetime(2026, 8, 6, 20, 0, tzinfo=timezone.utc)
    slots = covered_slots(now, _ts(2026, 8, 5, 20))  # 24h outage
    assert len(slots) == MAX_CATCHUP_HOURS
    assert slots[-1].hour == 20  # newest slots kept


def test_covered_slots_late_tick_floors_to_its_own_hour():
    # GitHub cron drift: the tick for 18:00 actually fires at 18:56. It must
    # cover slot 18, not be read as a partial 19:00 run.
    from delivery.scheduler import covered_slots
    now = datetime(2026, 8, 6, 18, 56, tzinfo=timezone.utc)
    slots = covered_slots(now, _ts(2026, 8, 6, 17))
    assert [s.hour for s in slots] == [18]


def test_covered_slots_empty_when_hour_already_covered():
    # Cron backstop fires at 17:56 after the 17:00 dispatch already ran.
    from delivery.scheduler import covered_slots
    now = datetime(2026, 8, 6, 17, 56, tzinfo=timezone.utc)
    assert covered_slots(now, _ts(2026, 8, 6, 17)) == []


@patch("delivery.scheduler.db.execute_many")
@patch("delivery.scheduler.db.execute")
def test_get_due_users_includes_user_due_at_a_backfilled_slot(mock_exec, mock_exec_many):
    # UTC 20:00 run backfilling 17:00-20:00. A UTC user is due at 18 (SVIP),
    # which only the backfilled slot matches — not the current hour.
    from delivery.scheduler import get_due_users, covered_slots
    now = datetime(2026, 8, 6, 20, 0, tzinfo=timezone.utc)
    future = int(now.timestamp()) + 86400
    mock_exec.return_value = [
        {"user_id": 3, "tier": "svip", "tier_expires_at": future, "timezone": "UTC"}
    ]
    slots = covered_slots(now, _ts(2026, 8, 6, 16))
    due = get_due_users(now, slots)
    assert len(due) == 1
    assert due[0]["user_id"] == 3


@patch("delivery.scheduler.db.execute_many")
@patch("delivery.scheduler.db.execute")
def test_get_due_users_returns_a_user_once_across_several_slots(mock_exec, mock_exec_many):
    # SVIP hours 10,14,18,22 — a 12h backfill would match twice; expect one entry
    # so a backfilled run delivers late, not one digest per missed slot.
    from delivery.scheduler import get_due_users
    now = datetime(2026, 8, 6, 22, 0, tzinfo=timezone.utc)
    future = int(now.timestamp()) + 86400
    mock_exec.return_value = [
        {"user_id": 4, "tier": "svip", "tier_expires_at": future, "timezone": "UTC"}
    ]
    slots = [
        datetime(2026, 8, 6, h, 0, tzinfo=timezone.utc) for h in (18, 19, 20, 21, 22)
    ]
    due = get_due_users(now, slots)
    assert len(due) == 1


@patch("delivery.scheduler.db.execute_many")
@patch("delivery.scheduler.db.execute")
def test_get_last_successful_run_reads_value(mock_exec, mock_exec_many):
    from delivery.scheduler import get_last_successful_run
    mock_exec.return_value = [{"value": 1234567890}]
    assert get_last_successful_run() == 1234567890
    # Table is created on read so no separate migration is needed
    assert "CREATE TABLE IF NOT EXISTS run_state" in mock_exec_many.call_args[0][0][0][0]


@patch("delivery.scheduler.db.execute_many")
@patch("delivery.scheduler.db.execute")
def test_get_last_successful_run_returns_none_on_db_error(mock_exec, mock_exec_many):
    from delivery.scheduler import get_last_successful_run
    mock_exec.side_effect = RuntimeError("Turso HTTP 500")
    assert get_last_successful_run() is None


@patch("delivery.scheduler.db.execute_many")
def test_record_successful_run_stores_floored_hour(mock_exec_many):
    from delivery.scheduler import record_successful_run
    now = datetime(2026, 8, 6, 18, 56, tzinfo=timezone.utc)
    record_successful_run(now)
    sql, args = mock_exec_many.call_args[0][0][1]
    assert "INSERT INTO run_state" in sql
    assert args[1] == _ts(2026, 8, 6, 18)  # floored, not 18:56


@patch("delivery.scheduler.db.execute_many")
def test_cleanup_seen_articles_deletes_old(mock_exec_many):
    from delivery.scheduler import cleanup_seen_articles, SEEN_RETENTION_SECONDS
    before = int(time.time())
    cleanup_seen_articles()
    sql, args = mock_exec_many.call_args[0][0][0]
    assert "DELETE FROM seen_articles" in sql
    cutoff = args[0]
    # cutoff ≈ now - retention
    assert abs((before - cutoff) - SEEN_RETENTION_SECONDS) < 5
