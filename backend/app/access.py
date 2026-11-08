"""The shared passcode: checking attempts and issuing and verifying the access cookie."""

import hashlib
import hmac
import time
from collections.abc import Callable

from app.limits import SlidingWindowLimiter

COOKIE_NAME = "lot_access"


class LoginRefused(Exception):
    """The passcode was wrong."""


class LoginLocked(Exception):
    """Too many wrong passcodes recently, so nothing is accepted for a while."""


class AccessGate:
    def __init__(
        self,
        passcode: str | None,
        secret: str,
        lifetime_seconds: int,
        failures: SlidingWindowLimiter,
        wall_clock: Callable[[], float] = time.time,
    ):
        self._passcode = passcode
        self._secret = secret.encode()
        self._lifetime = lifetime_seconds
        self._failures = failures
        self._wall_clock = wall_clock

    @property
    def required(self) -> bool:
        return self._passcode is not None

    def login(self, attempt: str) -> str | None:
        """Checks a passcode. Returns the cookie value, or None if no passcode is needed."""
        if self._passcode is None:
            return None
        # Checked first, so the right passcode cannot be found by guessing during a lockout.
        if self._failures.is_full():
            raise LoginLocked
        # compare_digest takes the same time however much of the attempt is correct.
        if not hmac.compare_digest(attempt.encode(), self._passcode.encode()):
            self._failures.record()
            raise LoginRefused
        expiry = str(int(self._wall_clock()) + self._lifetime)
        return f"{expiry}.{self._sign(expiry)}"

    def is_valid(self, token: str | None) -> bool:
        """True if the cookie was issued by this server and has not expired."""
        if self._passcode is None:
            return True
        if not token:
            return False
        expiry, _, signature = token.partition(".")
        if not hmac.compare_digest(signature.encode(), self._sign(expiry).encode()):
            return False
        # Only reached for a value we signed ourselves, so the expiry is a plain integer.
        return int(expiry) > self._wall_clock()

    def _sign(self, expiry: str) -> str:
        return hmac.new(self._secret, f"session:{expiry}".encode(), hashlib.sha256).hexdigest()
