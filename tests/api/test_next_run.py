"""GET /api/flows/{id}/next-run, and the schedule counting from the last real run (FR-15)."""

from datetime import UTC, datetime, timedelta

import pytest

from tests.api.test_lifecycle import make_client, run_and_wait, save_example  # noqa: F401  (fixture)


def next_run(client, flow_id):
    r = client.get(f"/api/flows/{flow_id}/next-run")
    assert r.status_code == 200, r.text
    value = r.json()["next_run_at"]
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


@pytest.mark.req("FR-15")
def test_next_run_is_shown_and_counts_from_the_last_run(make_client, fake_web):  # noqa: F811
    with make_client() as client:
        flow = save_example(client)  # interval: every 60 minutes
        assert next_run(client, flow["id"]) is None  # a draft has no schedule
        before = datetime.now(UTC)
        assert client.post(f"/api/flows/{flow['id']}/publish").status_code == 200
        due = next_run(client, flow["id"])
        assert before + timedelta(minutes=59) < due <= datetime.now(UTC) + timedelta(minutes=60)

        report = run_and_wait(client, flow["id"])  # Run now restarts the count
        ran_at = datetime.fromisoformat(report["started_at"].replace("Z", "+00:00"))
        assert abs(next_run(client, flow["id"]) - (ran_at + timedelta(minutes=60))) < timedelta(seconds=5)

        client.post(f"/api/flows/{flow['id']}/pause")
        assert next_run(client, flow["id"]) is None


@pytest.mark.req("FR-15")
def test_a_restart_keeps_the_next_run_from_the_last_run(make_client, fake_web):  # noqa: F811
    with make_client() as client:
        flow = save_example(client)
        client.post(f"/api/flows/{flow['id']}/publish")
        report = run_and_wait(client, flow["id"])
        ran_at = datetime.fromisoformat(report["started_at"].replace("Z", "+00:00"))
    with make_client() as restarted:  # same database, fresh app: the redeploy case
        due = next_run(restarted, flow["id"])
        assert abs(due - (ran_at + timedelta(minutes=60))) < timedelta(seconds=5)


def test_next_run_of_an_unknown_flow_is_404(make_client):  # noqa: F811
    with make_client() as client:
        assert client.get("/api/flows/nope/next-run").status_code == 404
