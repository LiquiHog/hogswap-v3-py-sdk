# Using HogSwap from your own scripts

New to this? [GETTING-STARTED.md](GETTING-STARTED.md) walks you through installing everything
and your first swap, step by step. This page is for when you're ready to write your own scripts.

You don't need to be a platform. With your own account you can script swaps, liquidity moves and
rebalances, and run them yourself.

## Setup

Put the `src/hogswap_v3` folder next to your script (or this repository's `src` folder on your
Python path), in an environment that has `py-algorand-sdk` for signing.

Keep your key out of your code:

- Put the 25-word mnemonic in an environment variable, or your OS keychain (e.g. the `keyring`
  package).
- Never commit it.
- Consider a separate account for scripts, holding only what they need.

```python
import os
from algosdk import account, mnemonic

from algosdk.v2client import algod as algod_client
from hogswap_v3 import HogswapClient, Algod, HogswapError, parse_units, sign_group, sign_transactions

key = mnemonic.to_private_key(os.environ["MY_MNEMONIC"])
me = account.address_from_private_key(key)
url = "https://mainnet-api.algonode.cloud"
hogswap, algod, client = HogswapClient(), Algod(url), algod_client.AlgodClient("", url)
```

## Quote, check, then send

[examples/my_swap.py](../examples/my_swap.py) shows the deal and asks before signing:

Load your words into the terminal first (see [GETTING-STARTED.md](GETTING-STARTED.md), step 5), then:

```sh
python examples/my_swap.py 0 31566704 25         # 25 ALGO -> USDC, then ask
python examples/my_swap.py 0 31566704 25 --yes   # no prompt (for schedulers)
```

The core of it:

```python
prepared = hogswap.prepare_swap(asset_in=0, asset_out=31566704, amount_in=parse_units("25", 6), sender=me)
# show prepared["quote"]["expected_out"], ["min_out_at_slippage"], ["router_fee_amount"] ...
algod.submit_and_confirm(sign_group(prepared["build"], key))
```

Always pass `sender=me`. If you hold HOG, your router fee discount shows up in the quote.

## Opt-ins

```python
from algosdk import transaction
opt_in = transaction.AssetTransferTxn(me, client.suggested_params(), me, 0, 31566704)
algod.submit_and_confirm(sign_transactions([opt_in], {me: key}))
```

Opting in locks 0.1 ALGO of minimum balance per asset, refunded if you opt out later.

## Repeating a trade (DCA)

```python
import time
while True:
    try:
        p = hogswap.prepare_swap(asset_in=31566704, asset_out=0, amount_in=5_000_000, sender=me)
        print(algod.submit_and_confirm(sign_group(p["build"], key)))
    except HogswapError as e:
        print(e.code, e)  # log it and try again next time
    time.sleep(3600)
```

## Good practice

- **Quote and send promptly.** A quote builds for about 30 seconds.
- **Keep slippage sensible:** 50 bps for most pairs.
- **Check your balance first**, including ALGO for `network_fee_max_microalgo` above your minimum
  balance.
- **Stay within the limits:** 30 quote and execute calls per 10 s from your IP. The client paces
  itself.
- **Use your own node** for `Algod(...)` if you run many scripts.
- **Try a tiny amount first.** `my_swap.py` always asks before sending unless you pass
  `--yes`; `bot_sign.py` stops before signing with `DRY_RUN=1`.

Liquidity works the same way: `quote_lp_mint` or `quote_lp_redeem`, then `execute`, sign, submit.
See [LP-AND-MULTI-ASSET.md](LP-AND-MULTI-ASSET.md) and [examples/lp.py](../examples/lp.py).
