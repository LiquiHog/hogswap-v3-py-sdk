# Routing options

By default the router searches every venue, up to 3 hops per path, and splits the trade over as
many pools as pays best. These options narrow or shape that search. All of them are optional.

| Option | Range | Default | What it does |
|---|---|---|---|
| `slippage_bps` | 1 to 5000 | 50 (0.5%) | How far below `expected_out_robust` (a slightly conservative `expected_out`) the group may settle. Sets `min_out_at_slippage`; below it the whole group reverts |
| `max_hops` | 1 to 4 | 3 | The most pools in a row on one path (A → B → C is 2 hops) |
| `max_legs` | 1 and up | none | The most pool legs in the whole route, across all paths |
| `max_outer_txns` | 3 to 16 | none | The most transactions in the built group |
| `exclude_venues` | venue keys | none | Venues the route must not use |
| `exclude_pools` | pool ids | none | Specific pools the route must not use |
| `allow_high_impact` | bool | False | LP deposits only: accept a deposit whose LP tokens are worth more than 2% less than the deposit |
| `cover_algo_fee` | bool | False | Pay the network fee out of the swap, so the user needs no spare ALGO |

## Slippage

The router plans against the latest block. By the time the user signs, prices may have moved.
`slippage_bps` is how much worse the user accepts.

- **Tight (10 to 30 bps):** for stable pairs and quick signing. More reverts when prices move.
- **Default (50 bps):** suits most pairs.
- **Wide (100+ bps):** for thin or volatile tokens. Reverts less, but the worst case is worse.

A revert costs nothing: the group is rejected, so nothing is swapped and no fee is charged.

## Hops

`max_hops` limits how many pools a single path can chain. More hops can find better prices through
an intermediate asset (for example TOKEN → ALGO → USDC). `max_hops=1` means direct pools only.

## Legs and group size

A route can split one trade over many pools; each pool used is a leg. More legs usually means a
better price on large trades, but also a bigger group and a higher network fee.

- **`max_legs`** caps the number of legs. The router finds the best route that fits.
- **`max_outer_txns`** caps the group's transaction count. The smallest swap group is 3
  transactions. Use it to keep room for your own transactions in the same atomic group (see
  [COMPOSING.md](COMPOSING.md)), or to keep the wallet prompt short.

A cap the trade can't fit returns `HogswapNoRouteError` with the reason.

Small trades rarely need either cap. On large trades, compare a capped quote against an uncapped
one before you choose.

## Excluding venues and pools

```python
from hogswap_v3 import VENUES

hogswap.quote(asset_in=0, asset_out=31566704, amount_in=amount, exclude_venues=["algofi_cp", "humble_v2"])
hogswap.quote(asset_in=0, asset_out=31566704, amount_in=amount, exclude_pools=[605929989])
```

| Key | Venue |
|---|---|
| `stamm` | STAMM pools (all fee tiers) |
| `tinyman_v2` | Tinyman v2 |
| `pact_cp` | Pact constant-product pools (v1 and v2) |
| `pact_stable` | Pact stableswap pools |
| `pact_weighted` | Pact weighted pools |
| `pact_clmm` | Pact concentrated-liquidity pools |
| `algofi_cp` | AlgoFi constant-product pools |
| `humble_v2` | Humble v2 |
| `biatec` | Biatec concentrated-liquidity pools |
| `folks_lend` | Folks Finance lending (deposit and withdraw fAssets) |
| `xalgo` | xALGO liquid staking (mint and burn) |
| `talgo` | tALGO liquid staking (mint and burn) |
| `dualstake` | DualSTAKE liquid staking (mint and redeem) |

`VENUES` in the SDK holds the same list. An unknown key returns an error naming the valid ones.
Each quote leg reports `dex_name` and `pool_id`, so you can see what a route used.

Typical reasons to exclude:
- a venue your users or your compliance rules don't accept;
- a pool you know is about to change;
- testing how much a venue adds to the price.

## High impact (LP deposits)

An LP deposit into a tier that is thin or priced away from the market can return LP tokens worth
noticeably less than what goes in. By default `quote_lp_mint` refuses a deposit that loses more than
2% (`lp_high_impact` in the error). `allow_high_impact=True` accepts it. Show the user
`lp.value_impact_bps` when you use it. Swaps aren't affected: their protection is `slippage_bps`.

## Covering the network fee

`cover_algo_fee=True` takes the network fee out of the swap instead of from the user's spare ALGO.
It's handy for users holding no ALGO. It applies to plain swaps, and can't be combined with a
referrer. The quote reports `cover_algo_fee_strategy` and `efficiency_loss_bps` (what covering
costs).

## The HOG holder discount

Pass `sender` (the wallet that will sign) on every quote. Wallets holding HOG pay a lower router
fee, and the quote reflects it in `router_fee_ppm_effective` and `hog_discount_pct`. Referred
quotes have no HOG discount.
