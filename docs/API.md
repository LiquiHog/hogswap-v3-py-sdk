# API reference

```python
from hogswap_v3 import HogswapClient, AsyncHogswapClient
hogswap = HogswapClient(**options)       # or AsyncHogswapClient(**options), same methods, awaitable
```

Responses are the API's JSON as dicts, unchanged: quantities are decimal strings (see
[AMOUNTS.md](AMOUNTS.md)). Errors are `HogswapError` subclasses (see
[LIMITS-AND-ERRORS.md](LIMITS-AND-ERRORS.md)).

Parameter types:

- *amount*: an `int` or a digit string, in base units.
- *id*: an `int` or a digit string.

## Options

| Option | Default | |
|---|---|---|
| `base_url` | `https://hogswap-v3.liquihog.dev` | |
| `timeout_s` | `20.0` | Per request |
| `retries` | `2` | For 429, 503, 425 and network errors (never `execute` network errors) |
| `rate_limit` | `(30, 10.0, 4)` | `(per_window, window_s, in_flight)`; `False` turns it off |
| `api_key` | `None` | Only if HogSwap issued you one |
| `headers` | `{}` | Extra headers on every request |

## Swaps

### `quote(*, asset_out, asset_in=None, amount_in=None, amount_out=None, ...)`

| Param | |
|---|---|
| `asset_in`, `asset_out` | ids |
| `amount_in` / `amount_out` | Exactly one (exact in / exact out) |
| `inputs` | 2 to 4 `{"asset_id", "amount"}`, a multi-input swap (replaces `asset_in` and the amount) |
| `extra_outputs` | 1 to 3 `{"asset_id", "amount"}`, a basket swap (exact in only) |
| `slippage_bps` | 1 to 5000, default 50 |
| `max_hops` | 1 to 4, default 3 |
| `max_legs`, `max_outer_txns` | Cap the route's legs / the group's transactions ([ROUTING-OPTIONS.md](ROUTING-OPTIONS.md), [COMPOSING.md](COMPOSING.md)) |
| `sender` | The signing account; includes its HOG fee discount |
| `referrer`, `fee_ppm` | Referral, plain swaps only; `fee_ppm` 0 to 10000 |
| `cover_algo_fee` | Take the network fee out of the swap |
| `exclude_venues`, `exclude_pools` | Venue keys (see `VENUES`) and pool ids to leave out |

**Key response fields:**
- `quote_id`
- `expected_out`, and `min_out_at_slippage` (the floor the group enforces)
- `legs`, `path_breakdown`
- `router_fee_amount`, `router_fee_ppm_effective`
- `network_fee_microalgo`, `network_fee_max_microalgo`
- on referred quotes: `referrer`, `referrer_fee_amount`, `referrer_share_ppm`

### `quote_lp_mint(*, pool_app_id, tier_index=None, amount_a=None, amount_b=None, external_inputs=None, ...)`

Deposit into a pool for its LP token. The response's `lp` has `expected_lp_out` and `lp_asset_id`. `allow_high_impact=True` accepts a deposit losing more than 2% of its value. Guide: [LP-AND-MULTI-ASSET.md](LP-AND-MULTI-ASSET.md).

### `quote_lp_redeem(*, pool_app_id, lp_amount, tier_index=None, target_asset=None, extra_outputs=None, ...)`

Return LP tokens for the pool's assets, or one `target_asset`. `lp["outputs"]` lists what you get.

### `execute(quote_id, user_address, *, prefix_txns=None, allow_warnings=False)`

The unsigned group for a quote, built for `user_address`. Nothing is signed or sent.

- `prefix_txns` (base64 or bytes) run before the group, and are simulated ahead of it only.
- **Response:** `unsigned_group` (`[{"txn_b64", "description"}]`), `group_id_b64`,
  `min_out_at_slippage`, `network_fee_microalgo`, `notes`, and `warnings` when the group would
  fail as it stands (raised as errors unless `allow_warnings=True`).

### `prepare_swap(*, sender, **quote_params)` → `{"quote", "build", "txns"}`

`quote` then `execute`; `txns` is the group as bytes.

## Referrals

| Method | |
|---|---|
| `referrer_status(referrer)` | Registration, discount token, `assets: [{asset_id, accrued, can_receive}]`, `terms`. Cached 10 s |
| `referrer_setup(referrer, *, assets=None, discount_token_id=None, discount_unit=None)` | Unsigned groups to open up to 200 assets (`MAX_REFERRER_ASSETS`) and/or set a discount token |
| `referrer_claim(referrer, *, assets=None, close=None, unregister=None)` | Unsigned groups paying out balances (up to 200 assets); `close=True` refunds deposits; `unregister=True` adds a last group that deletes the discount-token record and refunds its deposit (open assets keep earning; add `close=True` to leave entirely) |

Referrer responses:
- `groups: [{group_id_b64, steps, network_fee_microalgo, deposit_microalgo, unsigned_group}]`
- `group_shape`: `"batch"` (dozens of assets per group) or `"per_asset"`; sign and submit either
  the same way, in order
- `notes`

Sign each group with the platform's account and submit them in order.

## Market data

These calls aren't rate limited, but cache what you can.

| Method | Endpoint |
|---|---|
| `health()` | `GET /health` |
| `assets(*, limit=None, cursor=None, q=None)` | `GET /assets` (a page; `next_cursor` continues) |
| `assets_by_ids(ids)` | `GET /assets?ids=` |
| `asset(asset_id)` | `GET /assets/{id}` |
| `asset_pools(asset_id, *, sort=None)` | `GET /assets/{id}/pools` |
| `pools(*, limit, cursor, kind, asset_a, asset_b, min_tvl_algo_micro)` | `GET /pools` |
| `pool(pool_id)` | `GET /pools/{id}` |
| `prices(ids)` | `GET /prices?ids=` |
| `tvl()`, `tvl_assets(ids)` | `GET /tvl`, `GET /tvl/assets?ids=` |
| `stamm_pools(*, active_only=None, sort=None)` | `GET /stamm/pools` |
| `lp_token(lp_asset_id, *, amount=None)` | `GET /lp/{id}` |
| `lp_balance(*, pool_app_id, asset_id, amount, tier_index=None)` | `POST /lp/balance` |
| `analytics_prices()` | `GET /analytics/prices` |
| `iterate_assets(...)`, `iterate_pools(...)` | Every page (async iterators on the async client) |

## Submitting

```python
from hogswap_v3 import Algod, sign_group, group_base64, group_bytes, assert_fully_signed

algod = Algod("https://mainnet-api.algonode.cloud", token=None)
signed = sign_group(build, private_key)          # needs py-algorand-sdk
algod.submit_and_confirm(signed)                 # {"tx_id", "confirmed_round"}
```

| Function | |
|---|---|
| `group_base64(build)`, `group_bytes(build)` | The group as base64 strings or bytes |
| `assert_fully_signed(signed, n)` | One signed transaction per transaction, none missing |
| `sign_group(build, private_key)` | Sign with one account (py-algorand-sdk) |
| `compose_group(build, before=(), after=())` | Your algosdk transactions before and/or after the swap, one atomic group ([COMPOSING.md](COMPOSING.md), [AFTER-SWAP.md](AFTER-SWAP.md)) |
| `sign_transactions(txns, {address: key})` | Sign algosdk transactions, each with its sender's key |
| `final_txid(build)` | The swap group's last transaction id (py-algorand-sdk) |
| `received_from_swap(algod, final_tx_id, receiver, asset_id)` | What a confirmed swap paid ([AFTER-SWAP.md](AFTER-SWAP.md)) |
| `Algod(url, token=None, token_header="X-Algo-API-Token")` | `.submit(signed)`, `.wait_for_confirmation(tx_id)`, `.submit_and_confirm(signed)` |

## Amount helpers

`to_int`, `to_amount_int`, `to_amount_str`, `to_id`, `format_units`, `parse_units`,
`apply_slippage`.

## Constants

| Constant | Value |
|---|---|
| `ROUTER_APP_ID` | `3687031461` |
| `ALGO`, `USDC`, `HOG` | `0`, `31566704`, `3178895177` |
| `BASE_FEE_PPM` | `500` |
| `FEE_PPM_CAP` | `10000` |
| `RATE_LIMIT_PER_WINDOW`, `RATE_LIMIT_WINDOW_S`, `RATE_LIMIT_IN_FLIGHT` | `30`, `10.0`, `4` |
| `QUOTE_TTL_S` | `30` |
| `BUILDS_PER_QUOTE` | `5` |
| `MAX_GROUP_SIZE` | `16` |
| `MAX_REFERRER_ASSETS` | `200`: asset ids per referrer setup or claim request |
| `VENUES` | venue keys for `exclude_venues`, with descriptions |
