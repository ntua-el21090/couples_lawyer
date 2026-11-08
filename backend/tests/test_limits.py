"""A3, A4 and A5: caps on cases and lawyer calls, and expiry of old cases."""

import asyncio

from app.lawyer import BudgetedLawyer, LawyerError
from app.limits import SlidingWindowLimiter
from tests.conftest import DECISION, FakeLawyer

HEADER = "X-Seat-Token"
DAY = 24 * 60 * 60
TTL = 2 * 60 * 60


def open_case(client):
    """Creates a case with both seats claimed. Returns the id and each person's secret."""
    case_id = client.post("/api/cases").json()["id"]
    tokens = {
        person: client.post(f"/api/cases/{case_id}/seats", json={"person": person}).json()["token"]
        for person in ("boy", "girl")
    }
    return case_id, tokens


def say(client, case_id, tokens, person, route="statements", text="My side."):
    return client.post(
        f"/api/cases/{case_id}/{route}",
        json={"person": person, "text": text},
        headers={HEADER: tokens[person]},
    )


def test_limiter_counts_events_inside_its_window():
    now = [0.0]
    limiter = SlidingWindowLimiter(2, 10, clock=lambda: now[0])
    assert limiter.try_acquire() and limiter.try_acquire()
    assert not limiter.try_acquire()
    now[0] = 9.9
    assert limiter.is_full()
    now[0] = 10.1
    assert not limiter.is_full()
    assert limiter.try_acquire()


def test_a5_a_case_expires_after_two_hours_without_activity(make_client, clock):
    client, _ = make_client()
    case_id, _ = open_case(client)
    clock.advance(TTL - 1)
    assert client.get(f"/api/cases/{case_id}").status_code == 200
    clock.advance(2)
    assert client.get(f"/api/cases/{case_id}").status_code == 404


def test_a5_activity_keeps_a_case_alive_but_reading_does_not(make_client, clock):
    client, _ = make_client(DECISION)
    case_id, tokens = open_case(client)
    clock.advance(TTL - 60)
    assert client.get(f"/api/cases/{case_id}").status_code == 200  # a poll, not activity
    say(client, case_id, tokens, "boy")  # activity
    clock.advance(TTL - 60)
    assert client.get(f"/api/cases/{case_id}").status_code == 200
    clock.advance(120)
    assert client.get(f"/api/cases/{case_id}").status_code == 404


def test_a5_an_expired_case_accepts_nothing(make_client, clock):
    client, lawyer = make_client(DECISION)
    case_id, tokens = open_case(client)
    clock.advance(TTL + 1)
    assert say(client, case_id, tokens, "boy").status_code == 404
    assert client.post(f"/api/cases/{case_id}/retry", headers={HEADER: tokens["boy"]}).status_code == 404
    assert lawyer.calls == []


def test_a3_too_many_live_cases_are_refused_until_old_ones_expire(make_client, clock):
    client, _ = make_client(max_live_cases=2)
    assert client.post("/api/cases").status_code == 201
    assert client.post("/api/cases").status_code == 201
    full = client.post("/api/cases")
    assert full.status_code == 429
    assert "full" in full.json()["detail"].lower()

    clock.advance(TTL + 1)
    assert client.post("/api/cases").status_code == 201


def test_a3_ending_a_case_frees_its_place(make_client):
    client, _ = make_client(max_live_cases=1)
    case_id, tokens = open_case(client)
    assert client.post("/api/cases").status_code == 429
    client.delete(f"/api/cases/{case_id}", headers={HEADER: tokens["boy"]})
    assert client.post("/api/cases").status_code == 201


def test_a4_the_daily_cap_fails_the_case_with_a_clear_message_and_recovers(make_client, clock):
    ask = {"boy": "Why?"}
    # A long case lifetime, so this test checks the cap resetting and not the case expiring.
    client, lawyer = make_client(
        ask, DECISION, max_lawyer_calls_per_day=1, case_ttl_seconds=3 * DAY
    )
    case_id, tokens = open_case(client)
    say(client, case_id, tokens, "boy")
    after_girl = say(client, case_id, tokens, "girl").json()
    assert after_girl["status"] == "awaiting_answers"  # call 1 of 1

    blocked = say(client, case_id, tokens, "boy", "answers").json()
    assert blocked["status"] == "lawyer_failed"
    assert "limit" in blocked["error"].lower()
    assert len(lawyer.calls) == 1  # the capped call never reached the lawyer
    assert blocked["rounds"][0]["answers"] == {"boy": "My side."}  # nothing typed is lost

    clock.advance(DAY + 1)
    retried = client.post(f"/api/cases/{case_id}/retry", headers={HEADER: tokens["boy"]})
    assert retried.json()["status"] == "decided"


def test_a4_the_cap_is_shared_across_cases(make_client):
    client, lawyer = make_client(DECISION, max_lawyer_calls_per_day=2)
    outcomes = []
    for _ in range(3):
        case_id, tokens = open_case(client)
        say(client, case_id, tokens, "boy")
        outcomes.append(say(client, case_id, tokens, "girl").json()["status"])
    assert outcomes == ["decided", "decided", "lawyer_failed"]
    assert len(lawyer.calls) == 2


def test_a4_budgeted_lawyer_passes_calls_through_until_the_cap():
    inner = FakeLawyer(DECISION)
    lawyer = BudgetedLawyer(inner, SlidingWindowLimiter(1, 60))
    assert asyncio.run(lawyer.consult({}, True)) == DECISION
    try:
        asyncio.run(lawyer.consult({}, True))
    except LawyerError as error:
        assert "limit" in error.public_message.lower()
    else:
        raise AssertionError("the second call should have been refused")
    assert len(inner.calls) == 1
