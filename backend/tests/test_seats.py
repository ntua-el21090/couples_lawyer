"""F17 and F18: seats, and who may act for whom."""

import uuid

import pytest
from tests.conftest import DECISION

HEADER = "X-Seat-Token"


def create(client):
    response = client.post("/api/cases")
    assert response.status_code == 201
    return response.json()["id"]


def claim(client, case_id, person):
    return client.post(f"/api/cases/{case_id}/seats", json={"person": person})


def submit(client, case_id, person, token, route="statements", text="My side."):
    headers = {HEADER: token} if token is not None else {}
    return client.post(
        f"/api/cases/{case_id}/{route}", json={"person": person, "text": text}, headers=headers
    )


def test_f17_claiming_a_seat_returns_a_secret_and_marks_the_seat_taken(make_client):
    client, _ = make_client(DECISION)
    case_id = create(client)
    assert client.get(f"/api/cases/{case_id}").json()["seats_taken"] == {"boy": False, "girl": False}

    grant = claim(client, case_id, "boy")
    assert grant.status_code == 200
    assert grant.json()["person"] == "boy"
    assert len(grant.json()["token"]) >= 16
    assert client.get(f"/api/cases/{case_id}").json()["seats_taken"] == {"boy": True, "girl": False}


def test_f17_a_seat_can_only_be_claimed_once(make_client):
    client, _ = make_client(DECISION)
    case_id = create(client)
    assert claim(client, case_id, "boy").status_code == 200
    assert claim(client, case_id, "boy").status_code == 409
    assert claim(client, case_id, "girl").status_code == 200


def test_f17_each_seat_gets_a_different_secret(make_client):
    client, _ = make_client(DECISION)
    case_id = create(client)
    assert claim(client, case_id, "boy").json()["token"] != claim(client, case_id, "girl").json()["token"]


def test_f17_unknown_case_and_bad_person(make_client):
    client, _ = make_client(DECISION)
    assert claim(client, uuid.uuid4(), "boy").status_code == 404
    assert claim(client, create(client), "lawyer").status_code == 422


def test_f18_secrets_never_appear_in_the_case_view(make_client):
    client, _ = make_client(DECISION)
    case_id = create(client)
    tokens = [claim(client, case_id, person).json()["token"] for person in ("boy", "girl")]
    view = client.get(f"/api/cases/{case_id}").text
    assert not any(token in view for token in tokens)


@pytest.mark.parametrize("route", ["statements", "answers"])
def test_f18_no_secret_means_no_submission(make_client, route):
    client, lawyer = make_client(DECISION)
    case_id = create(client)
    claim(client, case_id, "boy")
    assert submit(client, case_id, "boy", None, route).status_code == 403
    assert lawyer.calls == []


@pytest.mark.parametrize("route", ["statements", "answers"])
def test_f18_a_wrong_secret_is_refused(make_client, route):
    client, _ = make_client(DECISION)
    case_id = create(client)
    claim(client, case_id, "boy")
    assert submit(client, case_id, "boy", "not-the-secret", route).status_code == 403


def test_f18_one_person_cannot_submit_as_the_other(make_client):
    client, _ = make_client(DECISION)
    case_id = create(client)
    boy = claim(client, case_id, "boy").json()["token"]
    girl = claim(client, case_id, "girl").json()["token"]
    assert submit(client, case_id, "girl", boy).status_code == 403
    assert submit(client, case_id, "boy", girl).status_code == 403
    # And the case is untouched, so the right people can still go ahead.
    assert submit(client, case_id, "boy", boy).status_code == 200


def test_f18_a_secret_for_one_case_does_not_work_on_another(make_client):
    client, _ = make_client(DECISION)
    first, second = create(client), create(client)
    token = claim(client, first, "boy").json()["token"]
    claim(client, second, "boy")
    assert submit(client, second, "boy", token).status_code == 403


def test_f18_a_secret_is_checked_before_the_state_of_the_case(make_client):
    client, _ = make_client(DECISION)
    case_id = create(client)
    boy = claim(client, case_id, "boy").json()["token"]
    submit(client, case_id, "boy", boy)
    # A repeat from the right person is a conflict, a repeat from a stranger is forbidden.
    assert submit(client, case_id, "boy", boy).status_code == 409
    assert submit(client, case_id, "boy", "stranger").status_code == 403


def test_f18_unknown_case_is_not_found_even_without_a_secret(make_client):
    client, _ = make_client(DECISION)
    assert submit(client, uuid.uuid4(), "boy", None).status_code == 404


def test_f18_retry_and_ending_a_case_need_a_seat(make_client):
    client, _ = make_client(DECISION)
    case_id = create(client)
    token = claim(client, case_id, "girl").json()["token"]
    assert client.post(f"/api/cases/{case_id}/retry").status_code == 403
    assert client.delete(f"/api/cases/{case_id}").status_code == 403
    assert client.delete(f"/api/cases/{case_id}", headers={HEADER: "nope"}).status_code == 403
    assert client.delete(f"/api/cases/{case_id}", headers={HEADER: token}).status_code == 204
    assert client.get(f"/api/cases/{case_id}").status_code == 404


def test_f18_a_non_ascii_secret_is_refused_not_a_crash(make_client):
    client, _ = make_client(DECISION)
    case_id = create(client)
    claim(client, case_id, "boy")
    response = client.post(
        f"/api/cases/{case_id}/statements",
        json={"person": "boy", "text": "Hi"},
        headers={HEADER: "σφάλμα".encode("utf-8")},
    )
    assert response.status_code == 403
