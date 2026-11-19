"""A backend swapping from its own account: quote, build, sign, submit.

    Needs py-algorand-sdk.
    (Load your 25 words into BOT_MNEMONIC first: docs/GETTING-STARTED.md, step 5. Never type them
    on the command line, where they'd land in your shell history.)
    ALGOD_URL="https://mainnet-api.algonode.cloud" python examples/bot_sign.py

This sends a real mainnet transaction (0.1 ALGO to USDC). Set DRY_RUN=1 to stop before signing.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from algosdk import account, mnemonic  # noqa: E402

from hogswap_v3 import ALGO, USDC, Algod, HogswapClient, HogswapMissingOptInError, format_units, sign_group  # noqa: E402

sk = mnemonic.to_private_key(os.environ["BOT_MNEMONIC"])  # never hard-code it
sender = account.address_from_private_key(sk)
algod = Algod(os.environ.get("ALGOD_URL", "https://mainnet-api.algonode.cloud"), token=os.environ.get("ALGOD_TOKEN"))
hogswap = HogswapClient()

try:
    prepared = hogswap.prepare_swap(asset_in=ALGO, asset_out=USDC, amount_in=100_000, slippage_bps=50, sender=sender)
except HogswapMissingOptInError as e:
    sys.exit(f"opt {sender} into asset(s) {e.assets} first")

quote, build = prepared["quote"], prepared["build"]
print(f"expect {format_units(quote['expected_out'], 6)} USDC, at least {format_units(build['min_out_at_slippage'], 6)}")
for t in build["unsigned_group"]:
    print(" ", t["description"])

if os.environ.get("DRY_RUN"):
    sys.exit(0)

result = algod.submit_and_confirm(sign_group(build, sk))
print(f"confirmed in round {result['confirmed_round']}: {result['tx_id']}")
