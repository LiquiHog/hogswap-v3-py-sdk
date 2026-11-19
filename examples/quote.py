"""A quote. Nothing is signed or sent.

    python examples/quote.py [amount-in-ALGO]
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hogswap_v3 import ALGO, USDC, HogswapClient, format_units, parse_units  # noqa: E402

hogswap = HogswapClient()
amount = sys.argv[1] if len(sys.argv) > 1 else "10"

algo, usdc = hogswap.assets_by_ids([ALGO, USDC])["assets"]
quote = hogswap.quote(asset_in=ALGO, asset_out=USDC, amount_in=parse_units(amount, algo["decimals"]), slippage_bps=50)

print(f"{amount} {algo['unit_name']} -> {format_units(quote['expected_out'], usdc['decimals'])} {usdc['unit_name']}")
print(f"worst case {format_units(quote['min_out_at_slippage'], usdc['decimals'])} {usdc['unit_name']} (slippage {quote['slippage_bps']} bps)")
print(f"router fee {format_units(quote['router_fee_amount'], usdc['decimals'])}, network fee up to {format_units(quote['network_fee_max_microalgo'], 6)} ALGO")
for leg in quote["legs"]:
    print(f"  {leg['dex_name']:<16} pool {leg['pool_id']}: {leg['asset_in']} -> {leg['asset_out']}")
