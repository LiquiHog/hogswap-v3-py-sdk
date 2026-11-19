"""The HogSwap v3 client (synchronous, standard library only)."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Union

from . import constants as C
from .amounts import AmountInput, to_amount_str, to_id
from .errors import (
    HogswapBuildError,
    HogswapError,
    HogswapInputError,
    HogswapMissingOptInError,
    HogswapNoRouteError,
    HogswapQuoteExpiredError,
    HogswapRateLimitError,
    HogswapUnavailableError,
)
from .group import group_bytes
from .limiter import RateLimiter

_ADDRESS = re.compile(r"^[A-Z2-7]{58}$")
ZERO_ADDRESS = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAY5HFKQ"

Id = Union[int, str]
Json = Any

#: (method, url, headers, body bytes, timeout) -> (status, headers, body bytes). Replaceable for tests.
Transport = Callable[[str, str, Dict[str, str], Optional[bytes], float], "tuple[int, Mapping[str, str], bytes]"]


def _urllib_transport(method: str, url: str, headers: Dict[str, str], body: Optional[bytes], timeout: float):
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers.items()), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers.items()) if e.headers else {}, e.read()


class HogswapClient:
    """Client for the HogSwap v3 API.

    Args:
        base_url: default ``https://hogswap-v3.liquihog.dev``.
        timeout_s: per request, default 20.
        retries: retries for rate-limit, busy and starting answers (and network errors, except on
            ``execute``), default 2.
        rate_limit: client-side pacing for quote, execute and referrer calls, as
            ``(per_window, window_s, in_flight)``. Default: the public limits. ``False`` turns it off.
        api_key: only if HogSwap issued you one. Keep it server-side.
        headers: extra headers on every request.

    Responses are the API's JSON as dicts, unchanged: quantities are decimal strings (convert with
    :func:`hogswap_v3.to_int`). The client is safe to share across threads.
    """

    def __init__(
        self,
        base_url: str = C.DEFAULT_BASE_URL,
        *,
        timeout_s: float = 20.0,
        retries: int = 2,
        rate_limit: Union[Sequence[float], bool, None] = None,
        api_key: Optional[str] = None,
        headers: Optional[Mapping[str, str]] = None,
        transport: Optional[Transport] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.retries = max(0, retries)
        self.api_key = api_key
        self.headers = {"User-Agent": "hogswap-v3-py-sdk", **dict(headers or {})}
        self._transport = transport or _urllib_transport
        if rate_limit is False:
            self.limiter: Optional[RateLimiter] = None
        else:
            per, window, inflight = rate_limit if isinstance(rate_limit, (list, tuple)) else (C.RATE_LIMIT_PER_WINDOW, C.RATE_LIMIT_WINDOW_S, C.RATE_LIMIT_IN_FLIGHT)
            self.limiter = RateLimiter(int(per), float(window), int(inflight))

    # ------------------------------------------------------------------ transport

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Mapping[str, Any]] = None,
        body: Any = None,
        limited: bool = False,
        retry_network: bool = True,
    ) -> Json:
        url = self.base_url + path
        q = {k: (",".join(str(x) for x in v) if isinstance(v, (list, tuple)) else str(v).lower() if isinstance(v, bool) else str(v)) for k, v in (query or {}).items() if v is not None and v != ""}
        if q:
            url += "?" + urllib.parse.urlencode(q)
        headers = {"Accept": "application/json", **self.headers}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()

        attempt = 0
        while True:
            release = self.limiter.acquire() if (limited and self.limiter) else None
            try:
                status, rheaders, raw = self._transport(method, url, headers, data, self.timeout_s)
            except (urllib.error.URLError, OSError) as e:
                if release:
                    release()
                if retry_network and attempt < self.retries:
                    time.sleep(min(0.5 * 2**attempt, 4.0))
                    attempt += 1
                    continue
                code = "timeout" if "timed out" in str(e).lower() else "network"
                raise HogswapError(f"{method} {path} failed: {e}", code=code) from None
            if release:
                release()
            parsed = _parse(raw)
            if 200 <= status < 300:
                return parsed
            err = to_error(status, rheaders, parsed, raw, path)
            if isinstance(err, HogswapRateLimitError) and self.limiter:
                self.limiter.pause(err.retry_after_s)
            if isinstance(err, (HogswapRateLimitError, HogswapUnavailableError)) and attempt < self.retries:
                time.sleep(err.retry_after_s)
                attempt += 1
                continue
            raise err

    # ------------------------------------------------------------------ swaps

    def health(self) -> Json:
        """GET /health: router status; ``ok`` is true once it's serving."""
        return self.request("GET", "/health")

    def quote(
        self,
        *,
        asset_out: Id,
        asset_in: Optional[Id] = None,
        amount_in: Optional[AmountInput] = None,
        amount_out: Optional[AmountInput] = None,
        inputs: Optional[Sequence[Mapping[str, Any]]] = None,
        extra_outputs: Optional[Sequence[Mapping[str, Any]]] = None,
        slippage_bps: Optional[int] = None,
        max_hops: Optional[int] = None,
        max_legs: Optional[int] = None,
        max_outer_txns: Optional[int] = None,
        sender: Optional[str] = None,
        referrer: Optional[str] = None,
        fee_ppm: Optional[int] = None,
        cover_algo_fee: bool = False,
        allow_high_impact: bool = False,
        exclude_venues: Optional[Sequence[str]] = None,
        exclude_pools: Optional[Sequence[Id]] = None,
    ) -> Json:
        """POST /quote for a swap.

        Give exactly one of ``amount_in`` (exact in) or ``amount_out`` (exact out), or ``inputs``
        (2-4 ``{"asset_id", "amount"}``) for a multi-input swap. ``extra_outputs`` (1-3) makes a
        basket swap. ``referrer`` and ``fee_ppm`` (0-10000) earn your platform part of the fee on
        plain swaps. Amounts are base units: ``int`` or a digit string.
        """
        body = _common(slippage_bps, max_hops, max_legs, max_outer_txns, sender, allow_high_impact)
        body["asset_out"] = to_id(asset_out, "asset_out")
        multi = bool(inputs)
        if multi:
            if asset_in is not None or amount_in is not None or amount_out is not None:
                raise HogswapInputError("inputs replace asset_in, amount_in and amount_out")
            if not 2 <= len(inputs) <= 4:  # type: ignore[arg-type]
                raise HogswapInputError("a multi-input swap takes 2 to 4 inputs")
            body["inputs"] = [_asset_amount(e, f"inputs[{i}]") for i, e in enumerate(inputs)]  # type: ignore[arg-type]
        else:
            if asset_in is None:
                raise HogswapInputError("asset_in is required")
            body["asset_in"] = to_id(asset_in, "asset_in")
            if (amount_in is None) == (amount_out is None):
                raise HogswapInputError("give exactly one of amount_in or amount_out")
            if amount_in is not None:
                body["amount_in"] = _positive(amount_in, "amount_in")
            else:
                body["amount_out"] = _positive(amount_out, "amount_out")  # type: ignore[arg-type]
        if extra_outputs:
            if len(extra_outputs) > 3:
                raise HogswapInputError("a basket swap takes 1 to 3 extra outputs")
            body["extra_outputs"] = [_asset_amount(e, f"extra_outputs[{i}]") for i, e in enumerate(extra_outputs)]
        if cover_algo_fee:
            body["cover_algo_fee"] = True
        if exclude_venues:
            body["exclude_venues"] = [str(v) for v in exclude_venues]
        if exclude_pools:
            body["exclude_pools"] = [to_id(p, "exclude_pools") for p in exclude_pools]
        if referrer is not None and referrer != ZERO_ADDRESS:
            body["referrer"] = _address(referrer, "referrer")
            if multi or extra_outputs or cover_algo_fee:
                raise HogswapInputError("a referrer applies to plain swaps only: one input, one output, no cover_algo_fee")
            if fee_ppm is not None:
                if isinstance(fee_ppm, bool) or not isinstance(fee_ppm, int) or not 0 <= fee_ppm <= C.FEE_PPM_CAP:
                    raise HogswapInputError(f"fee_ppm must be an integer 0-{C.FEE_PPM_CAP}")
                body["fee_ppm"] = fee_ppm
        elif fee_ppm is not None:
            raise HogswapInputError("fee_ppm needs a referrer")
        return self.request("POST", "/quote", body=body, limited=True)

    def quote_lp_mint(
        self,
        *,
        pool_app_id: Id,
        tier_index: Optional[int] = None,
        amount_a: Optional[AmountInput] = None,
        amount_b: Optional[AmountInput] = None,
        external_inputs: Optional[Sequence[Mapping[str, Any]]] = None,
        slippage_bps: Optional[int] = None,
        sender: Optional[str] = None,
        max_legs: Optional[int] = None,
        allow_high_impact: bool = False,
    ) -> Json:
        """POST /quote, mode LP_MINT: deposit into a pool for its LP token."""
        body: Dict[str, Any] = {"mode": "LP_MINT", "pool_app_id": to_id(pool_app_id, "pool_app_id")}
        body.update(_common(slippage_bps, None, max_legs, None, sender, allow_high_impact))
        if tier_index is not None:
            body["tier_index"] = _tier(tier_index)
        if amount_a is not None:
            body["amount_a"] = to_amount_str(amount_a, "amount_a")
        if amount_b is not None:
            body["amount_b"] = to_amount_str(amount_b, "amount_b")
        if external_inputs:
            body["external_inputs"] = [_asset_amount(e, f"external_inputs[{i}]") for i, e in enumerate(external_inputs)]
        if amount_a is None and amount_b is None and not external_inputs:
            raise HogswapInputError("quote_lp_mint needs amount_a, amount_b or external_inputs")
        return self.request("POST", "/quote", body=body, limited=True)

    def quote_lp_redeem(
        self,
        *,
        pool_app_id: Id,
        lp_amount: AmountInput,
        tier_index: Optional[int] = None,
        target_asset: Optional[Id] = None,
        extra_outputs: Optional[Sequence[Mapping[str, Any]]] = None,
        slippage_bps: Optional[int] = None,
        sender: Optional[str] = None,
        max_legs: Optional[int] = None,
        allow_high_impact: bool = False,
    ) -> Json:
        """POST /quote, mode LP_REDEEM: return LP tokens for the pool's assets (or one target asset)."""
        body: Dict[str, Any] = {"mode": "LP_REDEEM", "pool_app_id": to_id(pool_app_id, "pool_app_id"), "lp_amount": to_amount_str(lp_amount, "lp_amount")}
        body.update(_common(slippage_bps, None, max_legs, None, sender, allow_high_impact))
        if tier_index is not None:
            body["tier_index"] = _tier(tier_index)
        if target_asset is not None:
            body["target_asset"] = to_id(target_asset, "target_asset")
        if extra_outputs:
            outs = []
            for i, e in enumerate(extra_outputs):
                o: Dict[str, Any] = {"asset_id": to_id(e["asset_id"], f"extra_outputs[{i}].asset_id")}
                if e.get("amount") is not None:
                    o["amount"] = to_amount_str(e["amount"], f"extra_outputs[{i}].amount")
                outs.append(o)
            body["extra_outputs"] = outs
        return self.request("POST", "/quote", body=body, limited=True)

    def execute(
        self,
        quote_id: str,
        user_address: str,
        *,
        prefix_txns: Optional[Sequence[Union[str, bytes]]] = None,
        allow_warnings: bool = False,
    ) -> Json:
        """POST /execute: the unsigned group for a quote, built for ``user_address``.

        Nothing is signed or sent. A quote builds for about 30 s, at most 5 times; a network error
        here is never retried, since a retry would spend another build.

        If the group would fail as it stands, the build carries ``warnings`` and this raises the
        matching error: :class:`HogswapMissingOptInError` (with ``assets``) or
        :class:`HogswapBuildError` (code ``insufficient_balance``). ``allow_warnings=True``
        returns the build anyway, e.g. when you put the fix in front of the group yourself.
        """
        if not quote_id or not isinstance(quote_id, str):
            raise HogswapInputError("quote_id is required")
        body: Dict[str, Any] = {"quote_id": quote_id, "user_address": _address(user_address, "user_address")}
        if prefix_txns:
            import base64

            body["prefix_txns"] = [t if isinstance(t, str) else base64.b64encode(t).decode() for t in prefix_txns]
        build = self.request("POST", "/execute", body=body, limited=True, retry_network=False)
        if not allow_warnings:
            _raise_on_warnings(build)
        return build

    def prepare_swap(self, *, sender: str, **quote_params: Any) -> Dict[str, Any]:
        """Quote and build in one call. Returns ``{"quote", "build", "txns"}`` (txns as bytes)."""
        sender = _address(sender, "sender")
        quote = self.quote(sender=sender, **quote_params)
        build = self.execute(quote["quote_id"], sender)
        return {"quote": quote, "build": build, "txns": group_bytes(build)}

    # ------------------------------------------------------------------ referrals

    def referrer_status(self, referrer: str) -> Json:
        """GET /referrer/{address}: registration, discount token and balance per asset."""
        return self.request("GET", f"/referrer/{_address(referrer, 'referrer')}", limited=True)

    def referrer_setup(
        self,
        referrer: str,
        *,
        assets: Optional[Sequence[Id]] = None,
        discount_token_id: Optional[Id] = None,
        discount_unit: Optional[AmountInput] = None,
    ) -> Json:
        """POST /referrer/setup: unsigned groups to open assets for earning and/or set a discount token."""
        body: Dict[str, Any] = {"referrer": _address(referrer, "referrer")}
        if assets is not None:
            if len(assets) > C.MAX_REFERRER_ASSETS:
                raise HogswapInputError(f"assets takes at most {C.MAX_REFERRER_ASSETS} asset ids")
            body["assets"] = [to_id(a, f"assets[{i}]") for i, a in enumerate(assets)]
        if (discount_token_id is None) != (discount_unit is None):
            raise HogswapInputError("discount_token_id and discount_unit go together (0 and 0 = no discount)")
        if discount_token_id is not None:
            body["discount_token_id"] = to_id(discount_token_id, "discount_token_id")
        if discount_unit is not None:
            body["discount_unit"] = to_amount_str(discount_unit, "discount_unit")
        if "assets" not in body and "discount_token_id" not in body:
            raise HogswapInputError("referrer_setup needs assets, a discount token, or both")
        return self.request("POST", "/referrer/setup", body=body, limited=True)

    def referrer_claim(
        self,
        referrer: str,
        *,
        assets: Optional[Sequence[Id]] = None,
        close: Optional[bool] = None,
        unregister: Optional[bool] = None,
    ) -> Json:
        """POST /referrer/claim: unsigned groups paying out what the platform earned.

        Without ``assets``, every opened asset with a balance. ``close=True`` also deletes each
        asset's record and refunds its deposit. ``unregister=True`` adds a last group that deletes
        the platform's discount-token record and refunds its 22,500 microALGO deposit; open assets
        keep earning.
        """
        body: Dict[str, Any] = {"referrer": _address(referrer, "referrer")}
        if assets is not None:
            if len(assets) > C.MAX_REFERRER_ASSETS:
                raise HogswapInputError(f"assets takes at most {C.MAX_REFERRER_ASSETS} asset ids")
            body["assets"] = [to_id(a, f"assets[{i}]") for i, a in enumerate(assets)]
        if close is not None:
            body["close"] = bool(close)
        if unregister is not None:
            body["unregister"] = bool(unregister)
        return self.request("POST", "/referrer/claim", body=body, limited=True)

    # ------------------------------------------------------------------ market data (not rate limited)

    def assets(self, *, limit: Optional[int] = None, cursor: Optional[Union[str, int]] = None, q: Optional[str] = None) -> Json:
        """One page of assets; ``next_cursor`` continues."""
        return self.request("GET", "/assets", query={"limit": limit, "cursor": cursor, "q": q})

    def assets_by_ids(self, ids: Iterable[Id]) -> Json:
        return self.request("GET", "/assets", query={"ids": _ids(ids)})

    def asset(self, asset_id: Id) -> Json:
        return self.request("GET", f"/assets/{to_id(asset_id, 'asset_id')}")

    def asset_pools(self, asset_id: Id, *, sort: Optional[str] = None) -> Json:
        """Every pool holding the asset (large for major assets)."""
        return self.request("GET", f"/assets/{to_id(asset_id, 'asset_id')}/pools", query={"sort": sort})

    def pools(
        self,
        *,
        limit: Optional[int] = None,
        cursor: Optional[Union[str, int]] = None,
        kind: Optional[int] = None,
        asset_a: Optional[Id] = None,
        asset_b: Optional[Id] = None,
        min_tvl_algo_micro: Optional[AmountInput] = None,
    ) -> Json:
        return self.request(
            "GET",
            "/pools",
            query={
                "limit": limit,
                "cursor": cursor,
                "kind": kind,
                "asset_a": None if asset_a is None else to_id(asset_a, "asset_a"),
                "asset_b": None if asset_b is None else to_id(asset_b, "asset_b"),
                "min_tvl_algo_micro": None if min_tvl_algo_micro is None else to_amount_str(min_tvl_algo_micro, "min_tvl_algo_micro"),
            },
        )

    def pool(self, pool_id: Id) -> Json:
        return self.request("GET", f"/pools/{to_id(pool_id, 'pool_id')}")

    def prices(self, ids: Iterable[Id]) -> Json:
        return self.request("GET", "/prices", query={"ids": _ids(ids)})

    def tvl(self) -> Json:
        return self.request("GET", "/tvl")

    def tvl_assets(self, ids: Iterable[Id]) -> Json:
        return self.request("GET", "/tvl/assets", query={"ids": _ids(ids)})

    def stamm_pools(self, *, active_only: Optional[bool] = None, sort: Optional[str] = None) -> Json:
        """STAMM pools with their fee tiers."""
        return self.request("GET", "/stamm/pools", query={"active_only": active_only, "sort": sort})

    def lp_token(self, lp_asset_id: Id, *, amount: Optional[AmountInput] = None) -> Json:
        """What an LP token (and optionally a holding of it) is backed by."""
        return self.request("GET", f"/lp/{to_id(lp_asset_id, 'lp_asset_id')}", query={"amount": None if amount is None else to_amount_str(amount)})

    def lp_balance(self, *, pool_app_id: Id, asset_id: Id, amount: AmountInput, tier_index: Optional[int] = None) -> Json:
        body: Dict[str, Any] = {"pool_app_id": to_id(pool_app_id, "pool_app_id"), "asset_id": to_id(asset_id, "asset_id"), "amount": to_amount_str(amount)}
        if tier_index is not None:
            body["tier_index"] = _tier(tier_index)
        return self.request("POST", "/lp/balance", body=body)

    def analytics_prices(self) -> Json:
        return self.request("GET", "/analytics/prices")

    def iterate_assets(self, *, limit: Optional[int] = None, q: Optional[str] = None) -> Iterator[Dict[str, Any]]:
        """Every asset, page by page."""
        cursor: Optional[str] = None
        while True:
            page = self.assets(limit=limit, cursor=cursor, q=q)
            yield from page["assets"]
            cursor = page.get("next_cursor")
            if not cursor:
                return

    def iterate_pools(self, **filters: Any) -> Iterator[Dict[str, Any]]:
        """Every pool matching the filters of :meth:`pools`, page by page."""
        cursor: Optional[str] = None
        while True:
            page = self.pools(cursor=cursor, **filters)
            yield from page["pools"]
            cursor = page.get("next_cursor")
            if not cursor:
                return


# ---------------------------------------------------------------------- helpers


def _common(slippage_bps, max_hops, max_legs, max_outer_txns, sender, allow_high_impact) -> Dict[str, Any]:
    o: Dict[str, Any] = {}
    if slippage_bps is not None:
        if isinstance(slippage_bps, bool) or not isinstance(slippage_bps, int) or not 1 <= slippage_bps <= 5000:
            raise HogswapInputError("slippage_bps must be an integer 1-5000")
        o["slippage_bps"] = slippage_bps
    if max_hops is not None:
        if isinstance(max_hops, bool) or not isinstance(max_hops, int) or not 1 <= max_hops <= 4:
            raise HogswapInputError("max_hops must be an integer 1-4")
        o["max_hops"] = max_hops
    for name, v in (("max_legs", max_legs), ("max_outer_txns", max_outer_txns)):
        if v is not None:
            if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 1000:
                raise HogswapInputError(f"{name} must be a positive integer")
            o[name] = v
    if allow_high_impact:
        o["allow_high_impact"] = True
    if sender is not None:
        o["sender"] = _address(sender, "sender")
    return o


def _asset_amount(e: Mapping[str, Any], name: str) -> Dict[str, Any]:
    if not isinstance(e, Mapping) or "asset_id" not in e or "amount" not in e:
        raise HogswapInputError(f'{name} must be {{"asset_id", "amount"}}')
    return {"asset_id": to_id(e["asset_id"], f"{name}.asset_id"), "amount": _positive(e["amount"], f"{name}.amount")}


def _positive(v: AmountInput, name: str) -> str:
    s = to_amount_str(v, name)
    if s == "0":
        raise HogswapInputError(f"{name} must be greater than zero")
    return s


def _tier(v: int) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 5:
        raise HogswapInputError("tier_index must be an integer 0-5")
    return v


def _address(v: Any, name: str) -> str:
    if not isinstance(v, str) or not _ADDRESS.match(v.strip()):
        raise HogswapInputError(f"{name} must be a 58-character Algorand address")
    return v.strip()


def _ids(ids: Iterable[Id]) -> List[int]:
    out = [to_id(x, "ids") for x in ids]
    if not out:
        raise HogswapInputError("ids must not be empty")
    return out


def _raise_on_warnings(build: Json) -> None:
    """Raise for a build that would fail as it stands. Skipped when the caller's own prefix_txns
    could not be simulated (their warnings describe the group without them)."""
    warnings = build.get("warnings") if isinstance(build, dict) else None
    if not warnings or build.get("prefix_simulated") is False:
        return
    kw: Dict[str, Any] = {"status": 200, "detail": warnings, "body": build}
    for w in warnings:
        code = w.get("code") if isinstance(w, dict) else None
        if code == "missing_opt_in":
            raise HogswapMissingOptInError(w.get("detail", ""), assets=w.get("assets") or [], **kw)
        if code == "insufficient_balance":
            raise HogswapBuildError(w.get("detail", ""), code="insufficient_balance", **kw)
        if code == "simulate_failed":
            raise HogswapBuildError(w.get("detail", ""), **kw)
    # min_out_risk is returned, not raised: the group may still settle.


def _parse(raw: bytes) -> Json:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return raw.decode("utf-8", "replace")


def _detail_text(parsed: Json, raw: bytes) -> str:
    d = parsed.get("detail") if isinstance(parsed, dict) else None
    if isinstance(d, str):
        return d
    if isinstance(d, list):
        parts = []
        for x in d:
            if isinstance(x, dict):
                loc = x.get("loc") or []
                parts.append(": ".join(str(p) for p in ([loc[-1]] if loc else []) + [x.get("msg", "")] if p))
            else:
                parts.append(str(x))
        return "; ".join(parts)
    if isinstance(parsed, str):
        return parsed[:300]
    return raw[:300].decode("utf-8", "replace")


def _retry_after(headers: Mapping[str, str], fallback: float) -> float:
    for k, v in headers.items():
        if k.lower() == "retry-after":
            try:
                return min(max(float(v), 0.0), 60.0)
            except ValueError:
                return fallback
    return fallback


def to_error(status: int, headers: Mapping[str, str], parsed: Json, raw: bytes, path: str) -> HogswapError:
    """Map an HTTP error response to the matching error class."""
    msg = _detail_text(parsed, raw) or f"HTTP {status}"
    detail = parsed.get("detail") if isinstance(parsed, dict) else None
    kw: Dict[str, Any] = {"status": status, "detail": detail, "body": parsed}
    if status == 404:
        if path == "/quote":
            return HogswapNoRouteError(msg, **kw)
        if path == "/execute":
            return HogswapQuoteExpiredError(msg, **kw)
        return HogswapError(msg, code="not_found", **kw)
    if status == 409:
        return HogswapBuildError(msg, **kw)
    if status == 422:
        if isinstance(parsed, dict) and parsed.get("error") == "missing_opt_in":
            return HogswapMissingOptInError(msg, assets=parsed.get("assets") or [], **kw)
        return HogswapError(msg, code="invalid_request", **kw)
    if status == 425:
        return HogswapUnavailableError(msg, retry_after_s=2.0, code="starting", **kw)
    if status == 429:
        if "build budget" in msg.lower():
            return HogswapQuoteExpiredError(msg, code="build_budget_spent", **kw)
        return HogswapRateLimitError(msg, retry_after_s=_retry_after(headers, 2.0), **kw)
    if status == 503:
        return HogswapUnavailableError(msg, retry_after_s=_retry_after(headers, 1.0), code="busy", **kw)
    if status == 400:
        return HogswapError(msg, code="bad_request", **kw)
    if status == 401:
        return HogswapError(msg, code="unauthorized", **kw)
    if status == 502:
        return HogswapError(msg, code="upstream", **kw)
    return HogswapError(msg, **kw)
