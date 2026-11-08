import copy

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import Decision


class FakeLawyer:
    """Stands in for Claude. Plays back a script of replies and records each call.

    A script item can be a Decision, a questions dict, or an exception to raise.
    The last item repeats forever, so one item can model "always asks".
    """

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    async def consult(self, transcript, must_decide):
        self.calls.append({"transcript": copy.deepcopy(transcript), "must_decide": must_decide})
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(item, Exception):
            raise item
        return item


DECISION = Decision(verdict="girl", reasoning="She had a point.", advice="Talk it over.")


class Clock:
    """A clock the tests can move forward. Used for both timeouts and cookie expiry."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def make_client(clock):
    """Builds a TestClient whose lawyer follows the given script.

    Keyword arguments become Settings, so a test can turn on the passcode or lower a limit.
    With no settings, access is open, as in local development.
    """

    def build(*script, base_url="http://testserver", **settings):
        lawyer = FakeLawyer(*(script or (DECISION,)))
        app = create_app(Settings(**settings), lawyer=lawyer, clock=clock, wall_clock=clock)
        client = TestClient(app, base_url=base_url)
        client.seats = {}  # (case id, person) -> the secret that device was given
        return client, lawyer

    return build
