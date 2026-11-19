"""Your own transaction in the same atomic group as a swap: here, a small payment to a platform
address before the swap. Builds and prints the combined group; sends only with --send.

    Needs py-algorand-sdk.
    (Load your 25 words into MY_MNEMONIC first: docs/GETTING-STARTED.md, step 5. Never type them
    on the command line, where they'd land in your shell history.)
    PLATFORM_ADDRESS=... python examples/compose_before_swap.py [--send]
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from algosdk import account, encoding, mnemonic, transaction  # noqa: E402
from algosdk.v2client import algod as algod_client  # noqa: E402

from hogswap_v3 import MAX_GROUP_SIZE, Algod, HogswapClient, compose_group, sign_transactions  # noqa: E402

key = mnemonic.to_private_key(os.environ["MY_MNEMONIC"])
user = account.address_from_private_key(key)
url = os.environ.get("ALGOD_URL", "https://mainnet-api.algonode.cloud")
hogswap = HogswapClient()

# 1. Your transaction(s), from fresh params.
params = algod_client.AlgodClient(os.environ.get("ALGOD_TOKEN", ""), url).suggested_params()
mine = [transaction.PaymentTxn(user, params, os.environ["PLATFORM_ADDRESS"], 10_000)]

# 2. Quote with room for them; 3. build with them as prefix_txns.
quote = hogswap.quote(asset_in=0, asset_out=31566704, amount_in=1_000_000, sender=user, max_outer_txns=MAX_GROUP_SIZE - len(mine))
build = hogswap.execute(quote["quote_id"], user, prefix_txns=[encoding.msgpack_encode(t) for t in mine])

# 4. One group: yours first.
group = compose_group(build, mine)
for i, t in enumerate(group):
    print(f"{i}: {t.type} from {str(t.sender)[:8]}...")

if "--send" in sys.argv:
    print(Algod(url, token=os.environ.get("ALGOD_TOKEN")).submit_and_confirm(sign_transactions(group, {user: key})))
