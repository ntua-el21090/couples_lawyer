"""Data shapes shared by the API and the lawyer."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, StringConstraints

from app.config import MAX_TEXT_LENGTH

Person = Literal["boy", "girl"]
PEOPLE: tuple[Person, Person] = ("boy", "girl")

CaseStatus = Literal[
    "awaiting_statements",
    "deliberating",
    "awaiting_answers",
    "decided",
    "lawyer_failed",
]

CleanText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TEXT_LENGTH),
]


# The final ruling, and also the schema Claude fills in, so it has no docstring (the SDK
# would send it to Claude). A single verdict field means a tie cannot be expressed.
class Decision(BaseModel):
    verdict: Literal["boy", "girl", "safety_concern"]
    reasoning: str
    advice: str


class Submission(BaseModel):
    person: Person
    text: CleanText


class SeatClaim(BaseModel):
    person: Person


class SeatGrant(BaseModel):
    person: Person
    token: str  # the secret that proves a device holds this seat


class Login(BaseModel):
    passcode: Annotated[str, StringConstraints(min_length=1, max_length=200)]


class SessionView(BaseModel):
    required: bool
    authenticated: bool


class RoundView(BaseModel):
    number: int
    questions: dict[Person, str]
    answered: list[Person]
    answers: dict[Person, str] | None  # None until everyone addressed has answered


class CaseView(BaseModel):
    id: UUID
    status: CaseStatus
    max_rounds: int
    current_round: int
    awaiting: list[Person]
    submitted: dict[Person, bool]
    seats_taken: dict[Person, bool]
    statements: dict[Person, str] | None  # None until both people have submitted
    rounds: list[RoundView]
    decision: Decision | None
    error: str | None
