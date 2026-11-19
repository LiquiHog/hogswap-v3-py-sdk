"""A thread-safe client-side limiter matching the public API's per-IP limits."""

from __future__ import annotations

import collections
import threading
import time
from typing import Callable, Deque


class RateLimiter:
    """At most ``per_window`` request starts in any rolling ``window_s``, and at most ``in_flight``
    running at once. Callers over the limit wait their turn instead of being refused.

    One limiter per client. Every client on the same IP shares the server's limit, so a server
    should share one client across threads.
    """

    def __init__(self, per_window: int, window_s: float, in_flight: int, *, clock: Callable[[], float] = time.monotonic) -> None:
        if per_window < 1 or window_s <= 0 or in_flight < 1:
            raise ValueError("per_window, window_s and in_flight must be positive")
        self.per_window = per_window
        self.window_s = window_s
        self.in_flight = in_flight
        self._clock = clock
        self._starts: Deque[float] = collections.deque()
        self._running = 0
        self._cond = threading.Condition()

    def acquire(self) -> Callable[[], None]:
        """Block until a slot is free. Returns a release function to call once when done."""
        with self._cond:
            while True:
                now = self._clock()
                while self._starts and self._starts[0] <= now - self.window_s:
                    self._starts.popleft()
                if self._running < self.in_flight and len(self._starts) < self.per_window:
                    self._starts.append(now)
                    self._running += 1
                    break
                if len(self._starts) >= self.per_window:
                    wait = self._starts[0] + self.window_s - now
                else:
                    wait = None  # wait for a release
                self._cond.wait(timeout=None if wait is None else max(0.001, wait))
        released = False

        def release() -> None:
            nonlocal released
            with self._cond:
                if released:
                    return
                released = True
                self._running -= 1
                self._cond.notify_all()

        return release

    def pause(self, seconds: float) -> None:
        """Hold back new starts for ``seconds`` (after a 429, the server says how long)."""
        with self._cond:
            fake = self._clock() + seconds - self.window_s
            self._starts = collections.deque([fake] * self.per_window)
            self._cond.notify_all()
