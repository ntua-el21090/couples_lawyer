"""Case rules and in-memory storage. Nothing here knows about HTTP or Claude's API."""

import hmac
import logging
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from app.config import MAX_ROUNDS
from app.lawyer import Lawyer, LawyerError
from app.models import PEOPLE, CaseStatus, CaseView, Decision, Person, RoundView

logger = logging.getLogger(__name__)


class CaseNotFound(Exception):
    pass


class CaseConflict(Exception):
    """The action is not allowed in the case's current state."""


class SeatForbidden(Exception):
    """The caller does not hold the seat the action needs."""


class TooManyCases(Exception):
    pass


@dataclass
class Round:
    questions: dict[Person, str]
    answers: dict[Person, str] = field(default_factory=dict)

    @property
    def waiting_on(self) -> list[Person]:
        return [person for person in PEOPLE if person in self.questions and person not in self.answers]


@dataclass
class Case:
    id: UUID
    last_activity: float
    status: CaseStatus = "awaiting_statements"
    statements: dict[Person, str] = field(default_factory=dict)
    rounds: list[Round] = field(default_factory=list)
    decision: Decision | None = None
    error: str | None = None
    # The secret each seat's device was given. Never included in a view.
    seat_tokens: dict[Person, str] = field(default_factory=dict)

    @property
    def awaiting(self) -> list[Person]:
        if self.status == "awaiting_statements":
            return [person for person in PEOPLE if person not in self.statements]
        if self.status == "awaiting_answers":
            return self.rounds[-1].waiting_on
        return []


class CaseService:
    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        ttl_seconds: float = 2 * 60 * 60,
        max_cases: int = 50,
    ) -> None:
        self._cases: dict[UUID, Case] = {}
        self._clock = clock
        self._ttl = ttl_seconds
        self._max_cases = max_cases

    def create(self) -> Case:
        self._sweep()
        if len(self._cases) >= self._max_cases:
            raise TooManyCases
        case = Case(id=uuid4(), last_activity=self._clock())
        self._cases[case.id] = case
        return case

    def get(self, case_id: UUID) -> Case:
        """Finds a case. Reading it does not count as activity, so a forgotten open tab
        polling it cannot keep a case alive for ever."""
        case = self._cases.get(case_id)
        if case is None or self._expired(case):
            self._cases.pop(case_id, None)
            raise CaseNotFound
        return case

    def delete(self, case_id: UUID, seat_token: str | None) -> None:
        case = self.get(case_id)
        self._require_seat(case, seat_token)
        del self._cases[case_id]

    def claim_seat(self, case_id: UUID, person: Person) -> str:
        case = self.get(case_id)
        if person in case.seat_tokens:
            raise CaseConflict(f"The {person}'s seat is already taken.")
        token = secrets.token_urlsafe(16)
        case.seat_tokens[person] = token
        self._touch(case)
        return token

    async def submit_statement(
        self, case_id: UUID, person: Person, seat_token: str | None, text: str, lawyer: Lawyer
    ) -> Case:
        case = self.get(case_id)
        self._require_seat(case, seat_token, person)
        if person not in case.awaiting or case.status != "awaiting_statements":
            raise CaseConflict(f"The {person} cannot submit a statement right now.")
        case.statements[person] = text
        self._touch(case)
        if not case.awaiting:
            await self._deliberate(case, lawyer)
        return case

    async def submit_answer(
        self, case_id: UUID, person: Person, seat_token: str | None, text: str, lawyer: Lawyer
    ) -> Case:
        case = self.get(case_id)
        self._require_seat(case, seat_token, person)
        if person not in case.awaiting or case.status != "awaiting_answers":
            raise CaseConflict(f"The {person} is not being asked anything right now.")
        case.rounds[-1].answers[person] = text
        self._touch(case)
        if not case.awaiting:
            await self._deliberate(case, lawyer)
        return case

    async def retry(self, case_id: UUID, seat_token: str | None, lawyer: Lawyer) -> Case:
        case = self.get(case_id)
        self._require_seat(case, seat_token)
        if case.status != "lawyer_failed":
            raise CaseConflict("Only a failed consultation can be retried.")
        self._touch(case)
        await self._deliberate(case, lawyer)
        return case

    async def _deliberate(self, case: Case, lawyer: Lawyer) -> None:
        # Set before the await, so a duplicate request cannot start a second consultation,
        # and so the other person's device can see that the lawyer is at work.
        case.status = "deliberating"
        case.error = None
        must_decide = len(case.rounds) >= MAX_ROUNDS
        try:
            result = await lawyer.consult(transcript(case), must_decide)
        except LawyerError as exc:
            self._fail(case, exc.public_message)
            return
        except Exception as exc:  # any other error must not leave the case stuck
            logger.error("Unexpected lawyer failure: %s", type(exc).__name__)
            self._fail(case, "Something went wrong with the lawyer. Please try again.")
            return
        finally:
            self._touch(case)

        if isinstance(result, Decision):
            case.decision = result
            case.status = "decided"
        elif must_decide:  # the round limit holds even if the lawyer ignores it
            self._fail(case, "The lawyer failed to reach a ruling. Please try again.")
        else:
            case.rounds.append(Round(questions=result))
            case.status = "awaiting_answers"

    @staticmethod
    def _fail(case: Case, message: str) -> None:
        case.status = "lawyer_failed"
        case.error = message

    def _require_seat(self, case: Case, token: str | None, person: Person | None = None) -> None:
        """Checks the caller's secret. With `person`, it must be that person's secret."""
        holder: Person | None = None
        if token:
            candidate = token.encode()
            for seat, stored in case.seat_tokens.items():
                # compare_digest, and no early exit, so timing does not reveal a secret.
                if hmac.compare_digest(stored.encode(), candidate):
                    holder = seat
        if holder is None or (person is not None and holder != person):
            raise SeatForbidden("That seat isn't yours.")

    def _touch(self, case: Case) -> None:
        case.last_activity = self._clock()

    def _expired(self, case: Case) -> bool:
        return self._clock() - case.last_activity >= self._ttl

    def _sweep(self) -> None:
        for case_id in [c.id for c in self._cases.values() if self._expired(c)]:
            del self._cases[case_id]


def transcript(case: Case) -> dict[str, Any]:
    """The full record the lawyer reads on each consultation."""
    return {
        "opening_statements": dict(case.statements),
        "follow_up_rounds": [
            {"round": number, "questions": dict(round_.questions), "answers": dict(round_.answers)}
            for number, round_ in enumerate(case.rounds, start=1)
        ],
    }


def to_view(case: Case) -> CaseView:
    """The API's view of a case, which hides text until everyone has submitted."""
    both_submitted = all(person in case.statements for person in PEOPLE)
    return CaseView(
        id=case.id,
        status=case.status,
        max_rounds=MAX_ROUNDS,
        current_round=len(case.rounds),
        awaiting=case.awaiting,
        submitted={person: person in case.statements for person in PEOPLE},
        seats_taken={person: person in case.seat_tokens for person in PEOPLE},
        statements=dict(case.statements) if both_submitted else None,
        rounds=[
            RoundView(
                number=number,
                questions=round_.questions,
                answered=[person for person in PEOPLE if person in round_.answers],
                answers=dict(round_.answers) if not round_.waiting_on else None,
            )
            for number, round_ in enumerate(case.rounds, start=1)
        ],
        decision=case.decision,
        error=case.error,
    )
