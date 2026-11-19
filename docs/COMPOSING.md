# Adding your own transactions to a swap

You can put your own transactions in the same atomic group as a swap, before it, after it, or
both, so they succeed or fail together. Examples include:

- before: a payment to your platform, an opt-in the user needs first, a withdrawal that funds the
  swap;
- after: depositing the swap's output as collateral, repaying a loan, sending it on (see
  [AFTER-SWAP.md](AFTER-SWAP.md)).

## The rules

These come from the router contract:

1. **Before, after, or both, but never in between.** Nothing can go between the router's own
   transactions. `compose_group` keeps them together.
2. **One swap per group.** The router refuses a second route in the same group.
3. **At most 16 transactions in total.** Quote with
   `max_outer_txns=16 - len(before) - len(after)` so the swap leaves room.
4. **Order matters.** Transactions before the swap can't use its output (they can fund it,
   though: a withdrawal in front of the swap is fine).
   Transactions after it can also spend the swap's output, up to `min_out_at_slippage`.
5. **Every transaction needs its sender's signature.**
6. **Submit the whole group unchanged** after regrouping.

## Step by step

```python
from algosdk import encoding, transaction
from algosdk.v2client import algod
from hogswap_v3 import HogswapClient, Algod, compose_group, sign_transactions, MAX_GROUP_SIZE

hogswap = HogswapClient()
client = algod.AlgodClient("", "https://mainnet-api.algonode.cloud")
params = client.suggested_params()

# 1. Your transaction(s). Here: a 0.1 ALGO payment to your platform.
mine = [transaction.PaymentTxn(user, params, PLATFORM, 100_000)]

# 2. Quote with room for them.
quote = hogswap.quote(asset_in=0, asset_out=31566704, amount_in=10_000_000, sender=user,
                      max_outer_txns=MAX_GROUP_SIZE - len(mine))

# 3. Build, telling the router about them, so it checks the swap against the balances they leave.
build = hogswap.execute(quote["quote_id"], user,
                        prefix_txns=[encoding.msgpack_encode(t) for t in mine])

# 4. One group: yours first, then the swap, with a new group id.
group = compose_group(build, mine)

# 5. Sign each with its sender's key, then submit.
signed = sign_transactions(group, {user: user_key})
Algod("https://mainnet-api.algonode.cloud").submit_and_confirm(signed)
```

`compose_group(build, before, after)` clears the swap's old group id, puts `before` in front of
the swap and `after` behind it, and assigns one new group id to all of them. Pass either or both
(`compose_group(build, after=mine)` for after only). It and `sign_transactions` need
py-algorand-sdk.

## About `prefix_txns`

`prefix_txns` tells the router what runs before the swap. The router simulates them ahead of the
swap while building. (There's no equivalent for `after`: those run once the swap is done, so they
can't change how it's built.) They aren't returned or signed by the router; you still add them with
`compose_group`. If they can't run on current chain state, the build notes it
(`prefix_simulated: False`) and checks the swap alone.

## Mixed signers

When some transactions come from your platform's account and the rest from the user:

- **On your server,** `sign_transactions(group, {PLATFORM: platform_key, user: user_key})` covers
  both.
- **When the user signs in a browser wallet,** sign your own transactions on the server, send the
  unsigned rest to the frontend (`encoding.msgpack_encode(txn)` per transaction), and let the
  wallet sign those indexes. Combine the results in order before submitting.

## Fees and validity

- **Fees:** each of your transactions pays its own network fee (at least 0.001 ALGO).
- **Validity:** build them from fresh suggested params, and submit within about 30 seconds of the
  quote.

## Show users the whole group

A transaction placed after the swap can move the swap's output anywhere, and it's signed together
with the swap. So:

- **Builders:** show your users what each of your transactions does before they sign, and don't
  add anything they didn't ask for.
- **Wallets and users:** read every transaction in a swap's signing request, not only the swap.
  A transfer of the output to an address you don't recognise is a red flag.
