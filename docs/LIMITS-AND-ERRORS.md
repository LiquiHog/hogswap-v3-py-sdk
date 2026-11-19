# Limits and errors

## Rate limits

| Endpoint | Limit, per client IP |
|---|---|
| `POST /quote`, `POST /execute`, every `/referrer/...` call (GET included) | 30 requests per 10 s, shared; at most 4 running at once |
| Market data: `/assets`, `/prices`, `/pools`, `/tvl`, `/lp`, `/stamm/...`, `/health` | not rate limited |

- **Over the window:** `429` with `Retry-After` (seconds).
- **More than 4 at once:** `429`.
- **The router as a whole momentarily full:** `503` with `Retry-After: 1`.
- **Still starting after a restart:** `425`.

### What the client does for you

- **Paces itself:** `quote`, `execute` and `referrer_*` calls wait so they never exceed the
  window or the in-flight cap. The limiter is thread-safe, so share one client across threads.
  Turn it off with `HogswapClient(rate_limit=False)`, or set your own as
  `rate_limit=(per_window, window_s, in_flight)`.
- **Retries** (default 2 times) rate-limit, busy and starting answers after the server's
  `Retry-After`, and network errors on everything except `execute`.
- **Never retries `execute` after a network error**, because each build spends one of the
  quote's 5 builds.

### On a server

Every caller on your server's IP shares one limit. Share one client, cache market data, and where
users act in a browser, let the browser call the API directly (each visitor then has their own
limit).

## Quote lifetime

- A quote id is valid for about 30 seconds, and can be built at most 5 times.
- After that, `execute()` raises `HogswapQuoteExpiredError`. Its `code` is `quote_expired`, or
  `build_budget_spent` after 5 builds.
- Quote again.

## Builds that would fail as they stand

The router checks every build against current chain state. Problems it finds don't stop the
build, because you may fix some yourself in front of the group, but the build reports them in
`warnings`:

| Warning | Meaning | `execute()` raises |
|---|---|---|
| `missing_opt_in` | the user isn't opted into an output asset (`assets` lists them) | `HogswapMissingOptInError` |
| `insufficient_balance` | the user can't fund the group (balance or minimum balance) | `HogswapBuildError`, code `insufficient_balance` |
| `simulate_failed` | the group failed simulation for another reason (`detail` says why) | `HogswapBuildError`, code `build_failed` |
| `min_out_risk` | the swap settles just under `min_out_at_slippage` right now: prices are moving | no, it's returned; consider re-quoting |

- **Fixing it yourself,** for example with an opt-in in front of the group: pass that fix as
  `prefix_txns`. The build then checks the group with the fix applied, and the warning goes away.
- **`allow_warnings=True`** returns the build regardless.

## Error classes

Every error is a `HogswapError` with `status` (0 if no response), `code`, `detail` and `body`.

| Class | `code` | When | What to do |
|---|---|---|---|
| `HogswapInputError` (also a `ValueError`) | `invalid_input` | A bad argument, caught before sending | Fix the call |
| `HogswapNoRouteError` | `no_route` | `quote`: 404, no route fits | Smaller amount, another pair, more slippage |
| `HogswapQuoteExpiredError` | `quote_expired`, `build_budget_spent` | `execute`: the quote is gone | Quote again |
| `HogswapMissingOptInError` | `missing_opt_in` | `execute`: the account can't receive an output; `err.assets` lists them | Opt in, then quote again |
| `HogswapBuildError` | `build_failed`, `insufficient_balance` | `execute`: 409, simulation failed on current chain state | Check the balance, quote again |
| `HogswapRateLimitError` | `rate_limited` | 429 after retries; `err.retry_after_s` | Slow down |
| `HogswapUnavailableError` | `busy`, `starting` | 503 or 425 after retries | Retry shortly |
| `HogswapSubmitError` | `submit_failed`, `pool_error`, `timeout`, `network` | Your algod refused, rejected or didn't confirm | See the message; a `pool_error` is final |
| `HogswapError` | `invalid_request`, `bad_request`, `not_found`, `unauthorized`, `upstream`, `timeout`, `network` | Everything else | See `detail` |

```python
from hogswap_v3 import HogswapMissingOptInError, HogswapQuoteExpiredError

try:
    build = hogswap.execute(quote["quote_id"], address)
except HogswapMissingOptInError as e:
    opt_in(e.assets)
except HogswapQuoteExpiredError:
    requote()
```

## Network fees

- **`network_fee_microalgo`** is a typical fee for the group: an estimate.
- **`network_fee_max_microalgo`** is the most it can be. Check the account holds that much ALGO
  above its minimum balance.
- The router fee is taken from the swap output and reported as `router_fee_amount`.
