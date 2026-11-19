"""Use a swap's output in the same atomic group: swap ALGO to USDC, then send exactly the
guaranteed minimum on to another address (standing in for a deposit or repayment). One group, all
or nothing. Simulates the group first; sends only with --send.

    Needs py-algorand-sdk.
    (Load your 25 words into MY_MNEMONIC first: docs/GETTING-STARTED.md, step 5. Never type them
    on the command line, where they'd land in your shell history.)
    DEST_ADDRESS=... python examples/after_swap.py [--send]

DEST_ADDRESS must be opted into USDC, or the simulate fails and nothing is sent.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from algosdk import account, mnemonic, transaction  # noqa: E402
from algosdk.v2client import algod as algod_client  # noqa: E402
from algosdk.v2client.models import SimulateRequest, SimulateRequestTransactionGroup  # noqa: E402

from hogswap_v3 import ALGO, MAX_GROUP_SIZE, USDC, Algod, HogswapClient, compose_group, format_units, sign_transactions, to_int  # noqa: E402

key = mnemonic.to_private_key(os.environ["MY_MNEMONIC"])
me = account.address_from_private_key(key)
url = os.environ.get("ALGOD_URL", "https://mainnet-api.algonode.cloud")
token = os.environ.get("ALGOD_TOKEN", "")
node = algod_client.AlgodClient(token, url)
hogswap = HogswapClient()

# 1. Quote with room for the one transaction we add after the swap.
quote = hogswap.quote(asset_in=ALGO, asset_out=USDC, amount_in=1_000_000, sender=me, max_outer_txns=MAX_GROUP_SIZE - 1)
amount = to_int(quote["min_out_at_slippage"])
print(f"swap 1 ALGO -> at least {format_units(amount, 6)} USDC; then send exactly that on, in the same group")

# 2. Build the swap, and the step after it, sized to the guaranteed minimum.
build = hogswap.execute(quote["quote_id"], me)
after = [transaction.AssetTransferTxn(me, node.suggested_params(), os.environ["DEST_ADDRESS"], amount, USDC)]
group = compose_group(build, after=after)

# 3. Simulate the whole group: the router checks its swap, not the transactions you add.
req = SimulateRequest(
    txn_groups=[SimulateRequestTransactionGroup(txns=[transaction.SignedTransaction(t, None) for t in group])],
    allow_empty_signatures=True,
)
result = node.simulate_transactions(req)["txn-groups"][0]
if result.get("failure-message"):
    sys.exit(f"simulate failed at {result.get('failed-at')}: {result['failure-message']}")
print(f"simulate clean: {len(group)} transactions")
if "--send" not in sys.argv:
    sys.exit(0)

# 4. Sign and send.
signed = sign_transactions(group, {me: key})
print("confirmed", Algod(url, token=token or None).submit_and_confirm(signed))
