# Liquidity, multi-input and multi-output swaps

All of these follow the usual flow:

1. quote;
2. `execute(quote_id, address)`;
3. sign every transaction;
4. submit.

Only the quote call differs.

## Providing liquidity (LP deposit)

`quote_lp_mint` deposits into a pool and returns its LP token. Supported pools: STAMM (each fee
tier separately), Tinyman v2 and Pact weighted.

### Find a pool

```python
pools = hogswap.stamm_pools(active_only=True)["pools"]
pool = next(p for p in pools if p["asset_a"] == 0 and p["asset_b"] == 3178895177)  # ALGO/HOG
pool["extra"]["tiers"]  # [{"index", "fee_bps", "reserve_a", "reserve_b", "total_lp", "active"}, ...]
```

- **STAMM pools** have up to six fee tiers (`tier_index` 0 to 5). Each tier has its own reserves
  and its own LP token.
- **Other venues:** `pools(kind=..., asset_a=..., asset_b=...)` and `asset_pools(asset_id)` list
  them.

### Two-sided, one-sided, or from a third asset

```python
q = hogswap.quote_lp_mint(pool_app_id=3544790053, tier_index=1, amount_a=10_000_000, amount_b=4_700_000, sender=me)
q["lp"]["expected_lp_out"]   # LP tokens you receive (min: q["min_out_at_slippage"])
q["lp"]["lp_asset_id"]       # opt into this first
q["lp"]["deposit_trimmed"]   # True if part of one side was left out to match the ratio

hogswap.quote_lp_mint(pool_app_id=3544790053, tier_index=1, amount_a=10_000_000)  # one-sided: balanced for you
hogswap.quote_lp_mint(pool_app_id=3544790053, tier_index=1,
                      external_inputs=[{"asset_id": 31566704, "amount": 5_000_000}])  # from USDC
```

- **Value:** `lp["value_in_microalgo"]` and `lp["value_out_microalgo"]` compare what goes in with
  what the LP tokens are worth. `lp["value_impact_bps"]` is the difference.
- **More than 2% lost:** the quote is refused (`lp_high_impact`) unless you pass
  `allow_high_impact=True`.
- **Opt in first:** you must be opted into `lp["lp_asset_id"]` to receive LP tokens.

## Withdrawing liquidity (LP withdraw)

```python
q = hogswap.quote_lp_redeem(pool_app_id=3544790053, tier_index=1, lp_amount=1_000_000)
q["lp"]["outputs"]  # [{"asset_id": 0, "expected_out", "min_out_at_slippage"}, {"asset_id": 3178895177, ...}]

q = hogswap.quote_lp_redeem(pool_app_id=3544790053, tier_index=1, lp_amount=1_000_000, target_asset=0)
q["expected_out"]   # everything in ALGO
```

- **`extra_outputs`** (up to 3, `{"asset_id", "amount"?}`) settles part of the withdrawal in
  other assets. An entry without `amount` takes a whole side.
- **`lp_token(lp_asset_id, amount=...)`** shows what a holding is backed by, per asset and in USD.

## Multi-input swaps

```python
q = hogswap.quote(asset_out=31566704, inputs=[
    {"asset_id": 0, "amount": 10_000_000},          # 10 ALGO
    {"asset_id": 3178895177, "amount": 5_000_000},  # 5 HOG
])
```

- **Limits:** 2 to 4 distinct inputs, all different from `asset_out`.
- **Can't combine** with `extra_outputs`, `amount_out` or `cover_algo_fee`.

## Multi-output (basket) swaps

Give the **exact** amount of each extra asset. The rest of the input goes to `asset_out`:

```python
q = hogswap.quote(asset_in=0, amount_in=50_000_000, asset_out=31566704,
                  extra_outputs=[{"asset_id": 3178895177, "amount": 5_000_000}])  # exactly 5 HOG
q["extra_outputs"], q["expected_out"]  # the HOG, and the USDC from what's left
```

- **Limits:** 1 to 3 extra outputs, exact-in only.
- **Opt-ins:** you must be opted into every output.
- **No room:** if the extra targets use up the whole input, the quote is refused.

## Referrals

LP deposits and withdrawals, multi-input and basket swaps can't carry a referrer. Only plain swaps
can.
