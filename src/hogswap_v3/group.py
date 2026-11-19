"""Helpers for the unsigned groups that execute, referrer_setup and referrer_claim return.

HogSwap never signs or sends anything. You (or your user's wallet) sign every transaction in the
group, and you submit the signed group to an algod node you choose. Submitting needs no Algorand
SDK; :func:`sign_group` needs ``py-algorand-sdk``.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from .errors import HogswapInputError, HogswapSubmitError

GroupLike = Union[Mapping[str, Any], Sequence[Mapping[str, Any]]]


def group_base64(group: GroupLike) -> List[str]:
    """The group's transactions as base64 strings, in order.

    Accepts an execute response, one group from a referrer response, or the ``unsigned_group`` list.
    """
    items = group.get("unsigned_group") if isinstance(group, Mapping) else group
    if not isinstance(items, (list, tuple)) or not items:
        raise HogswapInputError("expected an unsigned group (unsigned_group: [{txn_b64}])")
    out = []
    for i, t in enumerate(items):
        b64 = t.get("txn_b64") if isinstance(t, Mapping) else None
        if not isinstance(b64, str):
            raise HogswapInputError(f"unsigned_group[{i}] has no txn_b64")
        out.append(b64)
    return out


def group_bytes(group: GroupLike) -> List[bytes]:
    """The group's transactions as msgpack bytes, in order."""
    return [base64.b64decode(b) for b in group_base64(group)]


def assert_fully_signed(signed: Sequence[Optional[bytes]], expected: int) -> List[bytes]:
    """Check there is one signed transaction per transaction in the group, none missing."""
    if len(signed) != expected:
        raise HogswapInputError(f"expected {expected} signed transactions, got {len(signed)}")
    for i, s in enumerate(signed):
        if not isinstance(s, (bytes, bytearray)) or not s:
            raise HogswapInputError(f"transaction {i} was not signed")
    return [bytes(s) for s in signed]  # type: ignore[arg-type]


def sign_group(group: GroupLike, private_key: str) -> List[bytes]:
    """Sign every transaction of the group with one account's private key (backends and bots).

    ``private_key`` is algosdk's base64 private key, e.g. from ``mnemonic.to_private_key(...)``.
    Needs ``py-algorand-sdk``.
    """
    try:
        from algosdk import encoding  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover - depends on the environment
        raise HogswapInputError("sign_group needs py-algorand-sdk (the algosdk package)") from e
    signed = []
    for b64 in group_base64(group):
        txn = encoding.msgpack_decode(b64)
        signed.append(base64.b64decode(encoding.msgpack_encode(txn.sign(private_key))))
    return signed


class Algod:
    """Where to submit: any mainnet algod (your own, or a hosted one).

    Args:
        url: e.g. ``"https://mainnet-api.algonode.cloud"``.
        token: sent in ``token_header`` when set.
        token_header: default ``"X-Algo-API-Token"``.
        timeout_s: per request, default 20.
    """

    def __init__(self, url: str, token: Optional[str] = None, token_header: str = "X-Algo-API-Token", timeout_s: float = 20.0) -> None:
        if not url:
            raise HogswapInputError("algod url is required")
        self.url = url.rstrip("/")
        self.headers: Dict[str, str] = {"User-Agent": "hogswap-v3-py-sdk"}
        if token:
            self.headers[token_header] = token
        self.timeout_s = timeout_s

    def _request(self, method: str, path: str, data: Optional[bytes] = None, content_type: Optional[str] = None) -> Any:
        headers = dict(self.headers)
        if content_type:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(self.url + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                body: Any = json.loads(raw)
                msg = body.get("message", raw[:300].decode("utf-8", "replace"))
            except (ValueError, AttributeError):
                body, msg = raw[:300].decode("utf-8", "replace"), raw[:300].decode("utf-8", "replace")
            raise HogswapSubmitError(f"algod {method} {path} failed (HTTP {e.code}): {msg}", status=e.code, body=body) from None
        except (urllib.error.URLError, OSError) as e:
            raise HogswapSubmitError(f"could not reach algod at {self.url}: {e}", code="network") from None
        return json.loads(raw) if raw else None

    def submit(self, signed: Sequence[bytes]) -> str:
        """Submit a fully signed group as one atomic group. Returns the first transaction's id."""
        signed = assert_fully_signed(signed, len(signed))
        res = self._request("POST", "/v2/transactions", b"".join(signed), "application/x-binary")
        tx_id = (res or {}).get("txId")
        if not tx_id:
            raise HogswapSubmitError("algod accepted the group but returned no txId", body=res)
        return tx_id

    def wait_for_confirmation(self, tx_id: str, timeout_s: float = 30.0, poll_s: float = 1.0) -> Dict[str, Any]:
        """Poll ``/v2/transactions/pending/{txid}`` until confirmed. Raises on a pool error or timeout."""
        deadline = time.monotonic() + timeout_s
        last: Optional[Exception] = None
        path = f"/v2/transactions/pending/{urllib.parse.quote(tx_id)}?format=json"
        while time.monotonic() < deadline:
            try:
                info = self._request("GET", path)
                if info.get("confirmed-round", 0) > 0:
                    return info
                if info.get("pool-error"):
                    raise HogswapSubmitError(f"transaction {tx_id} was rejected: {info['pool-error']}", body=info, code="pool_error")
            except HogswapSubmitError as e:
                if e.code == "pool_error":
                    raise
                last = e
            time.sleep(poll_s)
        raise HogswapSubmitError(f"transaction {tx_id} not confirmed within {timeout_s} s ({last})", code="timeout")

    def submit_and_confirm(self, signed: Sequence[bytes], timeout_s: float = 30.0) -> Dict[str, Any]:
        """Submit and wait. Returns ``{"tx_id", "confirmed_round"}``."""
        tx_id = self.submit(signed)
        info = self.wait_for_confirmation(tx_id, timeout_s=timeout_s)
        return {"tx_id": tx_id, "confirmed_round": info["confirmed-round"]}


def compose_group(group: GroupLike, before: Sequence[Any] = (), after: Sequence[Any] = ()) -> List[Any]:
    """Put your own transactions around a HogSwap group, as one atomic group: some before the
    swap, some after it, or both. Everything succeeds or fails together.

    Rules (enforced by the router contract):

    - ``before`` runs first, so it can't use the swap's output (it can fund the swap);
    - ``after`` runs once the swap has paid out, so it CAN spend the swap's output, up to
      ``min_out_at_slippage``, which the swap guarantees (e.g. deposit it as collateral);
    - nothing can go between the swap's own transactions, and only one swap fits in a group;
    - the whole group is at most 16 transactions: quote with
      ``max_outer_txns=16 - len(before) - len(after)``.

    ``before`` and ``after`` hold algosdk ``Transaction`` objects. Returns the combined list
    (before, the swap, after) with a fresh group id: sign each with its sender's key. Needs
    py-algorand-sdk.
    """
    try:
        from algosdk import encoding, transaction  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover - depends on the environment
        raise HogswapInputError("compose_group needs py-algorand-sdk (the algosdk package)") from e
    from .constants import MAX_GROUP_SIZE

    head, tail = list(before or ()), list(after or ())
    if not head and not tail:
        raise HogswapInputError("give at least one transaction in before or after")
    for name, txns in (("before", head), ("after", tail)):
        for i, t in enumerate(txns):
            if not isinstance(t, transaction.Transaction):
                raise HogswapInputError(f"{name}[{i}] must be an algosdk Transaction")
    swap = [encoding.msgpack_decode(b) for b in group_base64(group)]
    combined = head + swap + tail
    if len(combined) > MAX_GROUP_SIZE:
        raise HogswapInputError(
            f"the combined group would have {len(combined)} transactions (max {MAX_GROUP_SIZE}); quote with max_outer_txns={MAX_GROUP_SIZE - len(head) - len(tail)}"
        )
    # The old group id is part of each transaction's id, so clear it before computing the new one.
    for t in combined:
        t.group = None
    transaction.assign_group_id(combined)
    return combined


def sign_transactions(txns: Sequence[Any], keys: Mapping[str, str]) -> List[bytes]:
    """Sign algosdk Transactions (e.g. from :func:`compose_group`), each with its sender's key.

    ``keys`` maps sender address to algosdk private key. Returns signed bytes ready for
    :meth:`Algod.submit`. Needs py-algorand-sdk.
    """
    try:
        from algosdk import encoding  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover
        raise HogswapInputError("sign_transactions needs py-algorand-sdk") from e
    out = []
    for i, t in enumerate(txns):
        sender = str(t.sender)
        if sender not in keys:
            raise HogswapInputError(f"no key for transaction {i}'s sender {sender}")
        out.append(base64.b64decode(encoding.msgpack_encode(t.sign(keys[sender]))))
    return out


def final_txid(group: GroupLike) -> str:
    """The id of the swap group's last transaction (the router's final call). Needs py-algorand-sdk."""
    try:
        from algosdk import encoding  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover
        raise HogswapInputError("final_txid needs py-algorand-sdk") from e
    return encoding.msgpack_decode(group_base64(group)[-1]).get_txid()


def received_from_swap(algod: "Algod", final_tx_id: str, receiver: str, asset_id: int, timeout_s: float = 30.0) -> int:
    """What a confirmed swap actually paid ``receiver`` in ``asset_id`` (0 = ALGO), read from the
    router's final transaction (:func:`final_txid`). Use it to size a follow-up exactly.

    Call it soon after confirmation: nodes keep confirmed transactions in this view for a while,
    not forever.
    """
    info = algod.wait_for_confirmation(final_tx_id, timeout_s=timeout_s)
    total = 0

    def walk(node: Mapping[str, Any]) -> None:
        nonlocal total
        for it in node.get("inner-txns") or []:
            t = (it.get("txn") or {}).get("txn") or {}
            if asset_id == 0 and t.get("type") == "pay" and t.get("rcv") == receiver:
                total += int(t.get("amt", 0))
            if asset_id != 0 and t.get("type") == "axfer" and t.get("arcv") == receiver and int(t.get("xaid", 0)) == asset_id:
                total += int(t.get("aamt", 0))
            walk(it)

    walk(info)
    return total
