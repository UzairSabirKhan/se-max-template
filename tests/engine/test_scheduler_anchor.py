"""Interval schedules count from the last real run, so restarts and redeploys never push runs back (FR-15).

Before this, APScheduler counted each interval from when the job was added. Every redeploy rebuilt the
jobs, so a flow on a 30-minute interval never ran while deploys came more often than every 30 minutes.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.scheduler import CATCH_UP, trigger_for

FLOW = {"nodes": [{"id": "t1", "type": "trigger", "config": {"mode": "interval", "every_minutes": 30}}]}
LAST_RUN = datetime(2026, 11, 10, 9, 6, 21, tzinfo=UTC)


def first_fire(trigger, now):
    return trigger.get_next_fire_time(None, now)


@pytest.mark.req("FR-15")
def test_next_run_is_last_run_plus_the_interval_after_a_restart():
    restarted = LAST_RUN + timedelta(minutes=12)
    trigger = trigger_for(FLOW, LAST_RUN, now=restarted)
    assert first_fire(trigger, restarted) == LAST_RUN + timedelta(minutes=30)


@pytest.mark.req("FR-15")
def test_restarts_keep_the_same_next_run():
    for minutes in (1, 9, 17, 29):
        now = LAST_RUN + timedelta(minutes=minutes)
        assert first_fire(trigger_for(FLOW, LAST_RUN, now=now), now) == LAST_RUN + timedelta(minutes=30)


@pytest.mark.req("FR-15")
def test_a_run_that_came_due_while_the_app_was_down_runs_right_away():
    back = LAST_RUN + timedelta(minutes=42)  # the 09:36 run was missed during a redeploy
    assert first_fire(trigger_for(FLOW, LAST_RUN, now=back), back) == back + CATCH_UP


def test_after_the_first_tick_it_keeps_the_interval():
    now = LAST_RUN + timedelta(minutes=5)
    trigger = trigger_for(FLOW, LAST_RUN, now=now)
    first = first_fire(trigger, now)
    assert trigger.get_next_fire_time(first, first) == first + timedelta(minutes=30)


def test_no_last_run_counts_from_now_and_naive_times_are_utc():
    now = LAST_RUN
    assert first_fire(trigger_for(FLOW, None, now=now), now) == now + timedelta(minutes=30)
    naive = LAST_RUN.replace(tzinfo=None)  # what SQLite hands back
    later = LAST_RUN + timedelta(minutes=10)
    assert first_fire(trigger_for(FLOW, naive, now=later), later) == LAST_RUN + timedelta(minutes=30)


def test_manual_flows_have_no_trigger():
    manual = {"nodes": [{"id": "t1", "type": "trigger", "config": {"mode": "manual"}}]}
    assert trigger_for(manual, LAST_RUN) is None
