# Amounts

## The rules

1. **Amounts are base units.** 1 ALGO is `1000000` (6 decimals). Each asset has its own
   `decimals`; read it from `asset(id)` or `assets_by_ids(ids)`.
2. **The API sends quantities as decimal strings.** `expected_out`, `min_out_at_slippage`, fees,
   reserves, supplies and referral balances all arrive as strings like `"778891"`.
3. **Convert with `to_int()`** and do arithmetic on ints.
4. **Pass amounts as `int` or a digit string.** The SDK refuses floats and bools.

## Why

Algorand amounts go up to 2**64 - 1. Python's `int` is exact at any size, but a `float` is exact
only up to 2**53:

```python
float(18446744073709551615)        # 1.8446744073709552e+19: rounded
int(float("18446744073709551615")) # 18446744073709551616: wrong
```

Real assets cross that line: tokens with 18 decimals, or large supplies. Keep amounts out of
floats, including `json.loads(..., parse_float=...)` tricks, pandas columns of dtype `float64`, and
`round()`.

## Converting

```python
from hogswap_v3 import to_int, format_units, parse_units, to_amount_str

parse_units("12.5", 6)                      # 12500000: user input to base units
format_units("12500000", 6)                 # "12.5": base units to display
format_units(1999999, 6, max_decimals=2)    # "1.99": truncated, never rounded up
to_int(quote["expected_out"])               # int, or None passed through
to_amount_str(12500000)                     # "12500000": what the API takes
```

`parse_units` refuses more decimal places than the asset has.

## Handing amounts to JavaScript

A JavaScript `number` is exact only up to 2**53 - 1. If your backend sends amounts to a web
frontend, send them as **strings** (or keep the API's strings as they are), and parse them with
`BigInt` in the browser. `json.dumps({"amount": 18446744073709551615})` produces a JSON number
that browsers will round.

## pandas and numpy

`int64` overflows above 2**63 - 1, and `float64` rounds above 2**53. For amounts, keep `object`
columns of Python ints, or strings.

## Prices

`price_usd` and `price_algo` are decimal strings, for display; parse them with
`decimal.Decimal`, not `float`, if you calculate with them. `price_usd_micro` and
`price_algo_micro` are integer strings (millionths) for exact math.
