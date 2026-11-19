# Doing something with the swap's output

Swap into an asset, then use it right away: deposit it as collateral, repay a loan, add it to a
vault.

Your transactions can go **after** the swap in the same atomic group. They run once the swap has
paid out, so they can spend its output. If any of them fails, the whole group fails, swap
included, and the account keeps what it started with.

| | Before the swap | After the swap |
|---|---|---|
| Same atomic group | Yes | Yes |
| Can use | what the account already holds | the swap's output too |
| If your step fails | nothing happens at all | nothing happens at all |

## Pattern 1: one atomic group, sized to the guaranteed minimum

```python
from algosdk import encoding, transaction
from hogswap_v3 import USDC, HogswapClient, Algod, MAX_GROUP_SIZE, compose_group, sign_transactions, to_int

# Quote with room for your step (two transactions here).
quote = hogswap.quote(asset_in=0, asset_out=USDC, amount_in=amount_in, sender=me,
                      max_outer_txns=MAX_GROUP_SIZE - 2)
amount = to_int(quote["min_out_at_slippage"])  # the swap guarantees at least this

params = client.suggested_params()
after = [
    transaction.AssetTransferTxn(me, params, VAULT, amount, USDC),
    transaction.ApplicationNoOpTxn(me, params, YOUR_APP, app_args=[b"deposit"]),
]

build = hogswap.execute(quote["quote_id"], me)
group = compose_group(build, after=after)  # the swap, then yours, one group id

algod.submit_and_confirm(sign_transactions(group, {me: key}))
```

- **Anything above the minimum** stays in the account.
- **Don't spend more than `min_out_at_slippage`.** The swap may pay out exactly that. A step sized
  above it fails on a poor fill and takes the swap down with it.
- **Simulate the whole group** before signing (algod `simulate_transactions` with
  `allow_empty_signatures`). The router checks its own swap, not your transactions.
  [examples/after_swap.py](../examples/after_swap.py) shows how.

## Pattern 2: exact amount, a second group

To use every unit the swap paid, for example to close a loan to exactly zero, submit the swap on
its own, then read what it delivered:

```python
from hogswap_v3 import final_txid, received_from_swap, sign_group

algod.submit_and_confirm(sign_group(build, key))
received = received_from_swap(algod, final_txid(build), me, USDC)  # int, exact
# build and submit the follow-up for `received`
```

`received_from_swap` reads the router's final transaction from your node. Call it soon after
confirmation. `final_txid` needs py-algorand-sdk, and fits a swap sent on its own: once a swap
goes through `compose_group` it has a new group id, so take the final id from the composed
group instead (`group[len(before) + len(build["unsigned_group"]) - 1].get_txid()`).

These two steps are not atomic. If the follow-up fails, the swap stands and the account holds the
asset it swapped into.

## Both ends together

A position change often needs both ends in one group. For example: withdraw collateral, swap it,
and repay with the proceeds.

```python
quote = hogswap.quote(**swap, max_outer_txns=MAX_GROUP_SIZE - len(before) - len(after))
build = hogswap.execute(quote["quote_id"], me,
                        prefix_txns=[encoding.msgpack_encode(t) for t in before])
group = compose_group(build, before, after)
```

1. **Before:** the withdrawal (also passed as `prefix_txns`, so the router builds knowing it lands
   first).
2. **The swap.**
3. **After:** the repayment, sized to `min_out_at_slippage`.

All three succeed or fail together.

## Rules recap

- Nothing can go **between** the swap's own transactions. `compose_group` keeps them together.
- One swap per group.
- At most 16 transactions in total.
