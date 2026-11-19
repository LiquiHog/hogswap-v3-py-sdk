# hogswap-v3-py-sdk

Python SDK for the **HogSwap v3** router on Algorand.

- **Best-price swaps** across Algorand DEXes, split over many pools when that pays more.
- **Unsigned transaction groups** to sign with your own key or hand to a user's wallet.
- **The referral programme**: platforms earn part of the fee on every swap they send.
- **Market data**: assets, prices, pools, TVL and LP tokens.

Standard library only (Python 3.9+), with sync and asyncio clients and type hints.
Install `py-algorand-sdk` as well if you sign on a server or add your own transactions to a
swap.

HogSwap never holds keys. The router returns unsigned transactions; you or your user sign them,
and you submit them to an Algorand node you choose.

## Install

Copy the `src/hogswap_v3` folder into your project, or add this repository's `src` folder to your
Python path. The client needs nothing else. Signing on a server also needs `py-algorand-sdk`.

```python
import hogswap_v3
```

**New to this?** [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md) walks you through your first
swap from your own computer, step by step. Running a wallet, site or bot that wants to earn on
the swaps it sends? [docs/REFERRAL-WALKTHROUGH.md](docs/REFERRAL-WALKTHROUGH.md) goes from nothing
to your first claim.

## Quick start

```python
from hogswap_v3 import HogswapClient, ALGO, USDC, parse_units, format_units

hogswap = HogswapClient()

quote = hogswap.quote(asset_in=ALGO, asset_out=USDC, amount_in=parse_units("10", 6))

print("expected", format_units(quote["expected_out"], 6), "USDC")
print("at least", format_units(quote["min_out_at_slippage"], 6), "USDC")
```

## A full swap from a server account

```python
import os
from algosdk import account, mnemonic
from hogswap_v3 import HogswapClient, Algod, sign_group

hogswap = HogswapClient()
algod = Algod("https://mainnet-api.algonode.cloud")

sk = mnemonic.to_private_key(os.environ["BOT_MNEMONIC"])  # never hard-code it
address = account.address_from_private_key(sk)

prepared = hogswap.prepare_swap(asset_in=0, asset_out=31566704, amount_in=10_000_000, sender=address)
signed = sign_group(prepared["build"], sk)
result = algod.submit_and_confirm(signed)
print(result["tx_id"], result["confirmed_round"])
```

`prepare_swap` is `quote` then `execute`. The group is atomic, and the router reverts it if you
would receive less than `min_out_at_slippage`. Submit it exactly as built.

## Backends serving a web frontend

If your Python backend prepares swaps for users who sign in a browser wallet, pass the group to
the frontend as base64 strings (`group_base64(build)`) and let the wallet sign there. Never ask
users for keys.

Often the frontend can call the HogSwap API itself, with
[hogswap-v3-js-sdk](https://github.com/LiquiHog/hogswap-v3-js-sdk). Then each visitor has their
own rate limit, instead of every user sharing your server's IP. That SDK also documents Pera,
Defly, Lute and use-wallet.

## Amounts

Algorand amounts are 64-bit integers in base units. Python's `int` holds them exactly, so:

- the API returns quantities as **decimal strings**: convert with `to_int()`;
- pass amounts as an **int** or a **digit string**: floats are refused, because they're exact
  only up to 2**53;
- when you hand amounts to JavaScript, send them as **strings**.

```python
from hogswap_v3 import to_int, format_units

expected = to_int(quote["expected_out"])
worst = to_int(quote["min_out_at_slippage"])
format_units(expected - worst, 6)
```

[docs/AMOUNTS.md](docs/AMOUNTS.md) has the details.

## Referral programme

```python
quote = hogswap.quote(
    asset_in=0, asset_out=31566704, amount_in=10_000_000,
    referrer="YOUR_PLATFORM_ADDRESS", fee_ppm=5000,  # 0.5%, up to 10000 (1%)
)
quote["referrer_fee_amount"]  # your expected share of this swap

hogswap.referrer_setup("YOUR_PLATFORM_ADDRESS", assets=[0, 31566704])  # once per asset
hogswap.referrer_status("YOUR_PLATFORM_ADDRESS")                        # balances
hogswap.referrer_claim("YOUR_PLATFORM_ADDRESS")                         # unsigned claim groups
```

You keep half of the fee above the router's 0.05% base fee. [docs/REFERRALS.md](docs/REFERRALS.md)
covers the terms, deposits, discount tokens and claiming.

## Routing options

`slippage_bps`, `max_hops` (1 to 4), `max_legs`, `max_outer_txns` (group size), and
`exclude_venues` / `exclude_pools` (venue keys in `VENUES`).
[docs/ROUTING-OPTIONS.md](docs/ROUTING-OPTIONS.md) explains each one.

## Liquidity and multi-asset swaps

- `quote_lp_mint` and `quote_lp_redeem`: deposit and withdraw, two-sided, one-sided or from a
  third asset.
- `quote(inputs=[...])`: swap 2 to 4 assets into one.
- `quote(extra_outputs=[...])`: swap one asset into several.

See [docs/LP-AND-MULTI-ASSET.md](docs/LP-AND-MULTI-ASSET.md).

## Adding your own transactions

Put your own transactions before a swap, after it, or both, in one atomic group (16
transactions at most). Before: a payment, an opt-in, a withdrawal that funds the swap. After:
deposit the output as collateral, repay a loan, send it on.

```python
from algosdk import encoding
from hogswap_v3 import compose_group

# before, after: lists of algosdk Transactions (either may be empty)
quote = hogswap.quote(**swap, max_outer_txns=16 - len(before) - len(after))
build = hogswap.execute(quote["quote_id"], user, prefix_txns=[encoding.msgpack_encode(t) for t in before])
group = compose_group(build, before, after)  # one group id, all or nothing
```

Transactions after the swap can spend up to `min_out_at_slippage` of its output.
[docs/COMPOSING.md](docs/COMPOSING.md) has the rules; [docs/AFTER-SWAP.md](docs/AFTER-SWAP.md)
covers using the output, including the exact amount received.

## For your own scripts

Script swaps and liquidity from your own account: quote, check, confirm, send.
[docs/PERSONAL-USE.md](docs/PERSONAL-USE.md) and [examples/my_swap.py](examples/my_swap.py).

## Async

```python
from hogswap_v3 import AsyncHogswapClient

hogswap = AsyncHogswapClient()
quote = await hogswap.quote(asset_in=0, asset_out=31566704, amount_in=10_000_000)
async for asset in hogswap.iterate_assets():
    ...
```

## Limits

| What | Limit (per IP) |
|---|---|
| `quote`, `execute`, and all `referrer_*` calls | 30 per 10 s, shared; at most 4 at once |
| Market data (`assets`, `prices`, `pools`, ...) | not rate limited; cache what you can |
| A quote | builds for about 30 s, at most 5 times |

The client paces itself to these limits by default (thread-safe; share one client) and retries
rate-limit and busy answers. [docs/LIMITS-AND-ERRORS.md](docs/LIMITS-AND-ERRORS.md) lists every
error class.

## Reference

- [docs/API.md](docs/API.md): every method.
- [examples/](examples/): a quote, your own swap with a prompt, LP quotes, composing, a server-signed swap, and a referral platform.

## License

MIT
