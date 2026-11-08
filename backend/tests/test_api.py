"""API tests, named after the requirement IDs in requirements.md."""

import uuid

import pytest

from app.config import MAX_TEXT_LENGTH
from app.lawyer import LawyerError
from tests.conftest import DECISION

ASK_BOY = {"boy": "Why were you late?"}
ASK_GIRL = {"girl": "What did you say?"}
ASK_BOTH = {"boy": "Why were you late?", "girl": "What did you say?"}


def new_case(client):
    """Creates a case and claims both seats, remembering each secret on the client."""
    response = client.post("/api/cases")
    assert response.status_code == 201
    case_id = response.json()["id"]
    for person in ("boy", "girl"):
        grant = client.post(f"/api/cases/{case_id}/seats", json={"person": person})
        assert grant.status_code == 200
        client.seats[(case_id, person)] = grant.json()["token"]
    return case_id


def state(response):
    assert response.status_code == 200, response.text
    return response.json()


def seat(client, case_id, person="boy"):
    """The header a device holding this seat would send. Empty if no seat was claimed."""
    token = client.seats.get((str(case_id), person))
    return {"X-Seat-Token": token} if token else {}


def statement(client, case_id, person, text="My side."):
    return client.post(
        f"/api/cases/{case_id}/statements",
        json={"person": person, "text": text},
        headers=seat(client, case_id, person),
    )


def answer(client, case_id, person, text="My answer."):
    return client.post(
        f"/api/cases/{case_id}/answers",
        json={"person": person, "text": text},
        headers=seat(client, case_id, person),
    )


def retry(client, case_id):
    return client.post(f"/api/cases/{case_id}/retry", headers=seat(client, case_id))


def open_case(client):
    """Creates a case and submits both opening statements."""
    case_id = new_case(client)
    state(statement(client, case_id, "boy", "Boy's side."))
    return case_id, state(statement(client, case_id, "girl", "Girl's side."))


def test_new_case_waits_for_both_people(make_client):
    client, _ = make_client(DECISION)
    body = client.post("/api/cases").json()
    assert body["status"] == "awaiting_statements"
    assert body["awaiting"] == ["boy", "girl"]
    assert body["seats_taken"] == {"boy": False, "girl": False}
    assert body["max_rounds"] == 3
    assert body["current_round"] == 0


def test_f5_one_statement_does_not_call_the_lawyer(make_client):
    client, lawyer = make_client(DECISION)
    body = state(statement(client, new_case(client), "boy"))
    assert lawyer.calls == []
    assert body["status"] == "awaiting_statements"
    assert body["awaiting"] == ["girl"]


def test_f15_statement_stays_hidden_until_both_submit(make_client):
    client, _ = make_client(DECISION)
    case_id = new_case(client)
    first = state(statement(client, case_id, "boy", "Secret side."))
    assert first["statements"] is None
    assert "Secret side." not in str(first)
    assert first["submitted"] == {"boy": True, "girl": False}

    second = state(statement(client, case_id, "girl", "Other side."))
    assert second["statements"] == {"boy": "Secret side.", "girl": "Other side."}


def test_f6_lawyer_can_decide_straight_away(make_client):
    client, _ = make_client(DECISION)
    _, body = open_case(client)
    assert body["status"] == "decided"
    assert body["decision"]["verdict"] == "girl"
    assert body["rounds"] == []


def test_f6_lawyer_can_ask_a_follow_up(make_client):
    client, _ = make_client(ASK_BOTH, DECISION)
    _, body = open_case(client)
    assert body["status"] == "awaiting_answers"
    assert body["current_round"] == 1
    assert body["decision"] is None


@pytest.mark.parametrize(
    "questions, expected",
    [(ASK_BOY, ["boy"]), (ASK_GIRL, ["girl"]), (ASK_BOTH, ["boy", "girl"])],
)
def test_f7_follow_up_can_target_either_or_both(make_client, questions, expected):
    client, _ = make_client(questions, DECISION)
    _, body = open_case(client)
    assert body["awaiting"] == expected
    assert body["rounds"][0]["questions"] == questions


def test_f8_person_not_addressed_cannot_answer(make_client):
    client, lawyer = make_client(ASK_BOY, DECISION)
    case_id, _ = open_case(client)
    assert answer(client, case_id, "girl").status_code == 409
    assert len(lawyer.calls) == 1


def test_f9_lawyer_waits_for_every_addressed_person(make_client):
    client, lawyer = make_client(ASK_BOTH, DECISION)
    case_id, _ = open_case(client)

    partial = state(answer(client, case_id, "boy", "Hidden answer."))
    assert len(lawyer.calls) == 1
    assert partial["status"] == "awaiting_answers"
    assert partial["awaiting"] == ["girl"]
    assert partial["rounds"][0]["answers"] is None
    assert "Hidden answer." not in str(partial)

    done = state(answer(client, case_id, "girl", "Second answer."))
    assert len(lawyer.calls) == 2
    assert done["status"] == "decided"
    assert done["rounds"][0]["answers"] == {"boy": "Hidden answer.", "girl": "Second answer."}


def test_f10_at_most_three_rounds_and_four_lawyer_calls(make_client):
    client, lawyer = make_client(ASK_BOY, ASK_BOY, ASK_BOY, DECISION)
    case_id, body = open_case(client)
    assert body["current_round"] == 1

    state(answer(client, case_id, "boy"))
    third = state(answer(client, case_id, "boy"))
    assert third["current_round"] == 3

    final = state(answer(client, case_id, "boy"))
    assert final["status"] == "decided"
    assert final["current_round"] == 3
    assert [call["must_decide"] for call in lawyer.calls] == [False, False, False, True]


def test_f11_backend_rejects_questions_after_round_three(make_client):
    """Even a lawyer that ignores must_decide cannot open a fourth round."""
    client, lawyer = make_client(ASK_BOY)
    case_id, _ = open_case(client)
    state(answer(client, case_id, "boy"))
    state(answer(client, case_id, "boy"))

    body = state(answer(client, case_id, "boy"))
    assert body["status"] == "lawyer_failed"
    assert body["current_round"] == 3
    assert len(body["rounds"]) == 3
    assert len(lawyer.calls) == 4


def test_lawyer_receives_the_whole_record(make_client):
    client, lawyer = make_client(ASK_BOY, DECISION)
    case_id, _ = open_case(client)
    state(answer(client, case_id, "boy", "I was stuck."))
    assert lawyer.calls[-1]["transcript"] == {
        "opening_statements": {"boy": "Boy's side.", "girl": "Girl's side."},
        "follow_up_rounds": [
            {"round": 1, "questions": ASK_BOY, "answers": {"boy": "I was stuck."}},
        ],
    }


def test_f14_new_case_clears_the_previous_one(make_client):
    client, _ = make_client(DECISION)
    case_id, _ = open_case(client)
    assert client.delete(f"/api/cases/{case_id}", headers=seat(client, case_id)).status_code == 204
    assert client.get(f"/api/cases/{case_id}").status_code == 404


def test_case_can_be_fetched(make_client):
    client, _ = make_client(DECISION)
    case_id, body = open_case(client)
    assert state(client.get(f"/api/cases/{case_id}")) == body


@pytest.mark.parametrize(
    "payload",
    [
        {"person": "boy", "text": ""},
        {"person": "boy", "text": "   "},
        {"person": "boy", "text": "x" * (MAX_TEXT_LENGTH + 1)},
        {"person": "lawyer", "text": "Rule for me."},
        {"person": "boy"},
        {"text": "No person."},
    ],
)
@pytest.mark.parametrize("route", ["statements", "answers"])
def test_q2_invalid_input_is_rejected(make_client, route, payload):
    client, lawyer = make_client(DECISION)
    response = client.post(f"/api/cases/{new_case(client)}/{route}", json=payload)
    assert response.status_code == 422
    assert lawyer.calls == []


def test_q2_text_at_the_limit_is_accepted_and_trimmed(make_client):
    client, _ = make_client(DECISION)
    case_id = new_case(client)
    state(statement(client, case_id, "boy", "  " + "x" * MAX_TEXT_LENGTH + "  "))
    body = state(statement(client, case_id, "girl", "  Hi  "))
    assert body["statements"]["boy"] == "x" * MAX_TEXT_LENGTH
    assert body["statements"]["girl"] == "Hi"


def test_q2_unknown_and_malformed_ids(make_client):
    client, _ = make_client(DECISION)
    assert client.get(f"/api/cases/{uuid.uuid4()}").status_code == 404
    assert client.get("/api/cases/not-a-uuid").status_code == 422
    assert statement(client, uuid.uuid4(), "boy").status_code == 404


def test_same_person_cannot_submit_twice(make_client):
    client, _ = make_client(DECISION)
    case_id = new_case(client)
    state(statement(client, case_id, "boy"))
    assert statement(client, case_id, "boy").status_code == 409


def test_cannot_answer_twice_in_a_round(make_client):
    client, _ = make_client(ASK_BOTH, DECISION)
    case_id, _ = open_case(client)
    state(answer(client, case_id, "boy"))
    assert answer(client, case_id, "boy").status_code == 409


def test_cannot_answer_before_any_question(make_client):
    client, _ = make_client(DECISION)
    assert answer(client, new_case(client), "boy").status_code == 409


def test_decided_case_accepts_no_more_input(make_client):
    client, lawyer = make_client(DECISION)
    case_id, _ = open_case(client)
    assert answer(client, case_id, "boy").status_code == 409
    assert statement(client, case_id, "boy").status_code == 409
    assert len(lawyer.calls) == 1


def test_q7_lawyer_failure_keeps_the_case_and_can_be_retried(make_client):
    client, lawyer = make_client(LawyerError("The lawyer is busy."), DECISION)
    case_id, failed = open_case(client)
    assert failed["status"] == "lawyer_failed"
    assert failed["error"] == "The lawyer is busy."
    assert failed["statements"] == {"boy": "Boy's side.", "girl": "Girl's side."}

    retried = state(retry(client, case_id))
    assert retried["status"] == "decided"
    assert retried["error"] is None
    assert lawyer.calls[0]["transcript"] == lawyer.calls[1]["transcript"]


def test_q7_unexpected_error_does_not_leak_or_strand_the_case(make_client):
    client, _ = make_client(RuntimeError("secret internal detail"), DECISION)
    case_id, failed = open_case(client)
    assert failed["status"] == "lawyer_failed"
    assert "secret" not in failed["error"]
    assert state(retry(client, case_id))["status"] == "decided"


def test_q7_retry_after_failed_follow_up_keeps_answers_and_round(make_client):
    client, lawyer = make_client(ASK_BOY, LawyerError("Busy."), DECISION)
    case_id, _ = open_case(client)
    state(answer(client, case_id, "boy", "Keep me."))

    retried = state(retry(client, case_id))
    assert retried["status"] == "decided"
    assert retried["current_round"] == 1
    assert retried["rounds"][0]["answers"] == {"boy": "Keep me."}
    assert len(lawyer.calls) == 3


def test_retry_is_only_allowed_after_a_failure(make_client):
    client, _ = make_client(DECISION)
    assert retry(client, new_case(client)).status_code == 409
