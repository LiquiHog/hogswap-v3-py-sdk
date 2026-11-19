"""Exact amount handling.

Algorand amounts are unsigned 64-bit integers in base units. Python's ``int`` holds them exactly,
so the rules here are about the edges:

- the API sends every quantity as a decimal string: convert with :func:`to_int`;
- never route an amount through ``float``: floats are exact only up to 2**53;
- when you pass amounts on to JavaScript (a web frontend), send them as strings.
"""

from __future__ import annotations

import re
from typing import Optional, Union, overload

from .errors import HogswapInputError

UINT64_MAX = (1 << 64) - 1
_DIGITS = re.compile(r"^[0-9]+$")
_DECIMAL = re.compile(r"^([0-9]*)(?:\.([0-9]*))?$")

AmountInput = Union[int, str]


def to_amount_int(value: AmountInput, name: str = "amount") -> int:
    """A base-unit amount for a request: an ``int`` or a string of digits.

    Floats and bools are refused, so a rounded value can never reach the API.
    """
    if isinstance(value, bool):
        raise HogswapInputError(f"{name} must be an integer number of base units, not a bool")
    if isinstance(value, int):
        v = value
    elif isinstance(value, str):
        s = value.strip()
        if not _DIGITS.match(s):
            raise HogswapInputError(f'{name} must be a whole number of base units, got "{value}"')
        v = int(s)
    elif isinstance(value, float):
        raise HogswapInputError(f"{name} must be an int or a digit string; floats lose precision (got {value!r})")
    else:
        raise HogswapInputError(f"{name} must be an int or a digit string")
    if v < 0:
        raise HogswapInputError(f"{name} must not be negative")
    if v > UINT64_MAX:
        raise HogswapInputError(f"{name} exceeds the largest Algorand amount (2**64 - 1)")
    return v


def to_amount_str(value: AmountInput, name: str = "amount") -> str:
    """The decimal string the API expects for an amount."""
    return str(to_amount_int(value, name))


@overload
def to_int(value: None) -> None: ...
@overload
def to_int(value: Union[str, int]) -> int: ...
def to_int(value: Optional[Union[str, int]]) -> Optional[int]:
    """Parse an amount from an API response (a decimal string) into an ``int``. ``None`` passes through."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise HogswapInputError("expected an amount, got a bool")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.match(r"^-?[0-9]+$", value.strip()):
        return int(value.strip())
    raise HogswapInputError(f"{value!r} is not an integer amount")


def to_id(value: Union[int, str], name: str = "id") -> int:
    """An asset, app or pool id."""
    v = to_amount_int(value, name)
    return v


def format_units(amount: Union[int, str], decimals: int, *, max_decimals: Optional[int] = None, trim_zeros: bool = True) -> str:
    """Base units to a human-readable decimal string, exactly. ``format_units(1234567, 6) == "1.234567"``.

    ``max_decimals`` truncates (never rounds up).
    """
    _check_decimals(decimals)
    v = to_int(amount)
    neg = v < 0
    v = -v if neg else v
    base = 10**decimals
    whole = str(v // base)
    frac = str(v % base).rjust(decimals, "0") if decimals else ""
    if max_decimals is not None and max_decimals < len(frac):
        frac = frac[: max(0, max_decimals)]
    if trim_zeros:
        frac = frac.rstrip("0")
    return ("-" if neg else "") + whole + (f".{frac}" if frac else "")


def parse_units(text: str, decimals: int) -> int:
    """A human-readable decimal string to base units, exactly. ``parse_units("1.5", 6) == 1500000``.

    Raises if the text has more decimal places than the asset allows.
    """
    _check_decimals(decimals)
    s = str(text).strip().replace("_", "")
    m = _DECIMAL.match(s)
    if not m or (m.group(1) == "" and (m.group(2) or "") == ""):
        raise HogswapInputError(f'"{text}" is not a decimal amount')
    frac = m.group(2) or ""
    if len(frac.rstrip("0")) > decimals:
        raise HogswapInputError(f'"{text}" has more than {decimals} decimal places')
    v = int((m.group(1) or "0") + frac.ljust(decimals, "0")[:decimals])
    if v > UINT64_MAX:
        raise HogswapInputError(f'"{text}" exceeds the largest Algorand amount')
    return v


def apply_slippage(amount: Union[int, str], slippage_bps: int) -> int:
    """The amount left after slippage, rounded down. (A quote's ``min_out_at_slippage`` applies
    the slippage to ``expected_out_robust``, a slightly conservative ``expected_out``.)"""
    if isinstance(slippage_bps, bool) or not isinstance(slippage_bps, int) or not 0 <= slippage_bps <= 10_000:
        raise HogswapInputError("slippage_bps must be an integer 0-10000")
    return to_int(amount) * (10_000 - slippage_bps) // 10_000


def _check_decimals(decimals: int) -> None:
    if isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= 19:
        raise HogswapInputError("decimals must be an integer 0-19")
