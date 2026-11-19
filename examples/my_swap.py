"""Swap from your own account, with a confirmation prompt.

    Needs py-algorand-sdk.
    (Load your 25 words into MY_MNEMONIC first: docs/GETTING-STARTED.md, step 5. Never type them
    on the command line, where they'd land in your shell history.)
    python examples/my_swap.py <asset_in> <asset_out> <amount> [--yes]
    e.g.  python examples/my_swap.py 0 31566704 25     (25 ALGO -> USDC, asks before sending)

<amount> is in whole tokens ("25", "0.5"). Optional: ALGOD_URL, ALGOD_TOKEN, SLIPPAGE_BPS,
EXCLUDE_VENUES (comma-separated keys).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from algosdk import account, mnemonic  # noqa: E402

from hogswap_v3 import (  # noqa: E402
    Algod,
    HogswapClient,
    HogswapMissingOptInError,
    HogswapNoRouteError,
    format_units,
    parse_units,
    sign_group,
)

args = [a for a in sys.argv[1:] if not a.startswith("--")]
if len(args) != 3:
    sys.exit("usage: python examples/my_swap.py <asset_in> <asset_out> <amount> [--yes]")
asset_in, asset_out, amount_text = int(args[0]), int(args[1]), args[2]

key = mnemonic.to_private_key(os.environ["MY_MNEMONIC"])  # never hard-code it
me = account.address_from_private_key(key)
algod = Algod(os.environ.get("ALGOD_URL", "https://mainnet-api.algonode.cloud"), token=os.environ.get("ALGOD_TOKEN"))
hogswap = HogswapClient()

ain, aout = hogswap.asset(asset_in), hogswap.asset(asset_out)


def name(a):
    return a.get("unit_name") or f"asset {a['asset_id']}"


excl = os.environ.get("EXCLUDE_VENUES")
try:
    p = hogswap.prepare_swap(
        asset_in=asset_in,
        asset_out=asset_out,
        amount_in=parse_units(amount_text, ain["decimals"]),
        slippage_bps=int(os.environ.get("SLIPPAGE_BPS", "50")),
        exclude_venues=excl.split(",") if excl else None,
        sender=me,
    )
except HogswapMissingOptInError as e:
    sys.exit(f"opt in to asset(s) {e.assets} first")
except HogswapNoRouteError as e:
    sys.exit(f"no route: {e}")

q, d = p["quote"], aout["decimals"]
print(f"swap      {amount_text} {name(ain)} -> {format_units(q['expected_out'], d)} {name(aout)}")
print(f"at least  {format_units(q['min_out_at_slippage'], d)} {name(aout)} (or the swap reverts)")
print(f"fees      router {format_units(q['router_fee_amount'], d)} {name(aout)}, network up to {format_units(q['network_fee_max_microalgo'], 6)} ALGO")
print(f"route     {', '.join(leg['dex_name'] for leg in q['legs'])} ({len(q['legs'])} legs, {len(p['txns'])} txns)")

if "--yes" not in sys.argv and input("send it? [y/N] ").strip().lower() != "y":
    sys.exit(0)

r = algod.submit_and_confirm(sign_group(p["build"], key))
print(f"confirmed in round {r['confirmed_round']}: {r['tx_id']}")
