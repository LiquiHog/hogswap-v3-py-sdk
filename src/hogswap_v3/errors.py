"""Every error the SDK raises is a HogswapError."""

from __future__ import annotations

from typing import Any, List, Optional


class HogswapError(Exception):
    """An API or SDK error.

    Attributes:
        status: the HTTP status, or 0 when no response arrived.
        code: a stable machine-readable code, e.g. ``"rate_limited"``.
        detail: the server's ``detail`` field, when it sent one.
        body: the parsed response body, when there was one.
    """

    code = "error"

    def __init__(self, message: str, *, status: int = 0, detail: Any = None, body: Any = None, code: Optional[str] = None) -> None:
        super().__init__(message)
        self.status = status
        self.detail = detail
        self.body = body
        if code is not None:
            self.code = code


class HogswapInputError(HogswapError, ValueError):
    """A bad argument, caught before anything was sent."""

    code = "invalid_input"


class HogswapRateLimitError(HogswapError):
    """429: too many requests. ``retry_after_s`` says how long to wait."""

    code = "rate_limited"

    def __init__(self, message: str, *, retry_after_s: float = 1.0, **kw: Any) -> None:
        super().__init__(message, **kw)
        self.retry_after_s = retry_after_s


class HogswapUnavailableError(HogswapError):
    """425 or 503: the router is starting or momentarily busy. Safe to retry shortly."""

    code = "unavailable"

    def __init__(self, message: str, *, retry_after_s: float = 1.0, **kw: Any) -> None:
        super().__init__(message, **kw)
        self.retry_after_s = retry_after_s


class HogswapNoRouteError(HogswapError):
    """404 on /quote: no route fits this trade."""

    code = "no_route"


class HogswapQuoteExpiredError(HogswapError):
    """The quote expired (about 30 s) or used its 5 builds. Request a fresh quote."""

    code = "quote_expired"


class HogswapMissingOptInError(HogswapError):
    """422 on /execute: the wallet isn't opted into an asset it would receive.

    ``assets`` lists the asset ids to opt into before quoting again.
    """

    code = "missing_opt_in"

    def __init__(self, message: str, *, assets: Optional[List[int]] = None, **kw: Any) -> None:
        super().__init__(message, **kw)
        self.assets: List[int] = list(assets or [])


class HogswapBuildError(HogswapError):
    """409 on /execute: the group failed its simulation on current chain state."""

    code = "build_failed"


class HogswapSubmitError(HogswapError):
    """The algod node refused, rejected or didn't confirm a group."""

    code = "submit_failed"
