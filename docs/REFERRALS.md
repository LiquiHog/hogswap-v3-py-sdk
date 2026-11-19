# The referral programme

Setting up for the first time? [REFERRAL-WALKTHROUGH.md](REFERRAL-WALKTHROUGH.md) takes you
through it in order. This page is the reference.

For wallets, sites and bots that send swaps through HogSwap v3 (router app `3687031461`). You pass
your address and a fee rate with each quote, and you earn part of the fee on every swap you send.
Your earnings are held for you inside the router until you claim them.

## Terms

| | |
|---|---|
| Router base fee | 0.05% (500 ppm) of the swap output; always the router's |
| Your rate (`fee_ppm`) | up to 1% (10,000 ppm); anything below the base fee is raised to it |
| Your share | half of the fee above the base fee |
| Paid when | accrued in the router on each swap; claimed by you, any time |

On 1,000 ALGO of output:

| Your `fee_ppm` | User pays | Router keeps | You earn |
|---|---|---|---|
| 500 (base) | 0.50 | 0.50 | 0.00 |
| 5,000 (0.5%) | 5.00 | 2.75 | 2.25 |
| 10,000 (1%) | 10.00 | 5.25 | 4.75 |

Referred quotes apply to plain swaps: one input, one output, exact-in or exact-out. LP deposits
and withdrawals, multi-input, basket and cover-fee quotes can't carry a referrer, and the SDK
refuses them before sending.

## Discount token (optional)

Optional, and not needed to earn. You can set a token of your own: users who hold it pay a lower rate, in proportion to their
holding, down to the 0.05% base fee at the full holding you set. The discount reduces the whole
fee above the base, so it lowers your earnings and the router's equally. On 1,000 ALGO of output
at a 1% rate:

| User holds your token | User pays | Router keeps | You earn |
|---|---|---|---|
| none | 10.00 | 5.25 | 4.75 |
| half the full holding | 5.25 | 2.875 | 2.375 |
| the full holding | 0.50 | 0.50 | 0.00 |

## 1. Set up, once per asset

You earn in each swap's **output** asset, so open every asset your users are likely to buy:

```python
setup = hogswap.referrer_setup(referrer, assets=[0, 31566704, 386192725])
```

The response has `groups`: unsigned groups to sign with **your platform's wallet** and submit
in order. Each group lists its `steps` and its `deposit_microalgo`.

- **Up to 200 assets per request.** The router packs them into as few groups as it can: about 46
  to 53 assets per group (`group_shape: "batch"`), so 200 assets come to about four groups and four
  signatures. Each batch group is one deposit, one call that opens every asset in it, and small
  reference-only calls that carry the asset records. Only your wallet signs them.
- **`group_shape: "per_asset"`** means one payment and one call per asset, and at most 64 assets
  per request. The router falls back to it only if its contract lacks the batch methods; handle
  both shapes the same way: sign each group, submit in order.

- **Deposit per asset:** 0.0225 ALGO, refunded when you close it. The first platform to open an
  asset also pays 0.0097 ALGO for the asset's shared record, which every platform earning in it
  relies on, so that part isn't refunded.
- **Until an asset is open**, your share on swaps paying out in it goes to the router. The swap
  itself always completes.
- **To claim an asset**, your wallet must also be opted into it.

Set a discount token at the same time or later. The first one takes a 0.0225 ALGO deposit,
refunded when you remove it (section 4); changing it later costs nothing:

```python
hogswap.referrer_setup(referrer, discount_token_id=123456789, discount_unit=1_000_000_000)
```

`discount_unit` is the holding, in the token's base units, that gives the full discount.

## 2. Send swaps with your address and rate

```python
quote = hogswap.quote(
    asset_in=0, asset_out=31566704, amount_in=10_000_000,
    referrer=referrer, fee_ppm=5000,
)
```

`expected_out` and `min_out_at_slippage` already include your rate. The quote also reports:

- `referrer_fee_amount`: your expected share of this swap, in base units of the output asset;
- `referrer_share_ppm`: that share as ppm of the output, `(rate - 500) / 2`;
- `router_fee_ppm_effective`: the rate the user pays.

Leave out `fee_ppm` and the quote runs at the 500 ppm base, where you earn nothing.

Quotes don't apply your discount token. Users who hold it pay less than
`router_fee_ppm_effective` and receive at least `expected_out`, and your share of their swap is
lower than `referrer_fee_amount`.

Build with `execute()` as usual; the user signs the group with their wallet. No HOG holder
discount applies to referred swaps.

## 3. Check and claim

```python
status = hogswap.referrer_status(referrer)
# status["assets"]: [{"asset_id", "accrued", "can_receive"}]; accrued is a decimal string

claim = hogswap.referrer_claim(referrer)          # claims every asset with a balance
# or referrer_claim(referrer, assets=[31566704]), or close=True to also refund deposits
```

Sign each group with your platform's wallet and submit in order. `claim["notes"]` explains anything
skipped (nothing accrued, not opted in, not open).

- **Batch claims** carry about 30 to 35 assets per group (up to 200 per request).
- **With `close=True`** there are no separate claims: each asset is one close call that
  pays out its balance and refunds its deposit (16 per group). It covers every open asset,
  including those with nothing accrued.

Status is cached for 10 seconds per address. A setup or claim for that address refreshes it, so
polling faster gains nothing. A 502 means the router couldn't read the chain just then: retry it,
and never read it as "not registered".

## 4. Removing your discount token, or leaving

There's no sign-up to undo. You earn on every asset you've opened, whether or not you've set a
discount token. The only record "registering" creates is your discount-token setting.

`unregister=True` adds a last group that deletes that record and refunds its 0.0225 ALGO deposit.
Afterwards:

- swaps you refer charge the full rate you ask for, with no holder discount;
- your open assets keep earning, and you can still claim and close them;
- setting a discount token again pays the deposit again.

Without an asset list, a claim covers every asset with a balance, so to remove only the discount
token, pass `assets=[]` as well.

To leave entirely, add `close=True`. That pays out every balance, refunds every 0.0225 ALGO
deposit, and leaves none of your records in the router. Before you do:

- **Opt in to every asset with a balance.** An asset you aren't opted into can't be paid out,
  so it's skipped: its record, balance and deposit stay until you opt in and close it.
  `notes` lists any skipped asset.
- **Expect one call per asset.** Closes aren't batched: 16 fit in a group, so 100 open assets
  take 7 signatures. Each costs 0.003 ALGO in fees against its 0.0225 ALGO refund.

Swaps that still name your address afterwards complete normally, and your share of them goes
to the router.

```python
hogswap.referrer_claim(referrer, assets=[], unregister=True)   # remove the discount token only
hogswap.referrer_claim(referrer, close=True, unregister=True)  # leave entirely
```

## What the router guarantees

- **Only you can claim your balance.** Claims are keyed to the sending account.
- **A claim moves exactly your balance**, by plain transfer. It never touches the router's other
  holdings.
- **The router's owner can't take what it owes referrers.** Its fee sweep is blocked from balances
  owed to platforms.
- **Your setup can't break a user's swap.** If an asset isn't open,
  the swap still completes and only your share for that swap goes to the router. Opting in
  matters only when you claim.
- **Nothing here holds your keys.** Every call returns unsigned transactions.

## Contract reference

Router app `3687031461`, ABI methods:

- `register_referrer(uint64,uint64)void`, `unregister_referrer()void`;
- `open_referrer_asset(uint64)void`, `open_referrer_assets(uint64[])void`;
- `claim_referrer(uint64)void`, `claim_referrer_assets(uint64[])void`;
- `close_referrer_asset(uint64)void`.

Each swap emits a `ReferrerAccrued` or `ReferrerUnpaid` event, each claim a `ReferrerClaimed`
event, and an unregister a `ReferrerUnregistered` event, if you want to index your own history.
