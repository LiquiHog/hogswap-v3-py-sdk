"""Liquidity quotes on a STAMM pool: deposit (two-sided and one-sided) and withdraw.
Quote only: nothing is signed or sent.

    python examples/lp.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hogswap_v3 import HogswapClient, format_units  # noqa: E402

hogswap = HogswapClient()
POOL, TIER = 3544790053, 1  # STAMM ALGO/HOG, tier 1

pool = next(p for p in hogswap.stamm_pools(active_only=True)["pools"] if p["pool_id"] == POOL)
print(f"pool {POOL}: {pool['asset_a']}/{pool['asset_b']}")
for t in pool["extra"]["tiers"]:
    print(f"  tier {t['index']}: fee {t['fee_bps']} bps, active {t['active']}")

two = hogswap.quote_lp_mint(pool_app_id=POOL, tier_index=TIER, amount_a=10_000_000, amount_b=4_700_000)
lp = two["lp"]
print(f"deposit 10 ALGO + 4.7 HOG -> {format_units(lp['expected_lp_out'], 6)} LP (token {lp['lp_asset_id']}), value impact {lp['value_impact_bps']} bps")

one = hogswap.quote_lp_mint(pool_app_id=POOL, tier_index=TIER, amount_a=10_000_000)
print(f"deposit 10 ALGO only -> {format_units(one['lp']['expected_lp_out'], 6)} LP")

both = hogswap.quote_lp_redeem(pool_app_id=POOL, tier_index=TIER, lp_amount=1_000_000)
print("withdraw 1 LP -> " + " + ".join(f"{format_units(o['expected_out'], 6)} of {o['asset_id']}" for o in both["lp"]["outputs"]))

algo = hogswap.quote_lp_redeem(pool_app_id=POOL, tier_index=TIER, lp_amount=1_000_000, target_asset=0)
print(f"withdraw 1 LP all as ALGO -> {format_units(algo['expected_out'], 6)} ALGO")
