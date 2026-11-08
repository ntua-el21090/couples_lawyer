"""A counter of events inside a sliding time window, used for the app's caps."""

import time
from collections import deque
from collections.abc import Callable


class SlidingWindowLimiter:
    """Allows at most `max_events` events in any `window_seconds` period.

    The limits are global, not per caller. Behind Render's proxy a caller's address is
    easy to fake, so a per-address limit could be dodged.
    """

    def __init__(
        self, max_events: int, window_seconds: float, clock: Callable[[], float] = time.monotonic
    ):
        self._max = max_events
        self._window = window_seconds
        self._clock = clock
        self._events: deque[float] = deque()

    def _prune(self) -> None:
        cutoff = self._clock() - self._window
        while self._events and self._events[0] <= cutoff:
            self._events.popleft()

    def is_full(self) -> bool:
        self._prune()
        return len(self._events) >= self._max

    def record(self) -> None:
        self._events.append(self._clock())

    def try_acquire(self) -> bool:
        """Records an event and returns True, or returns False if the window is full."""
        if self.is_full():
            return False
        self.record()
        return True
