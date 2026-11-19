"""The referral programme from a platform's side, start to finish: where you stand, opening the
assets you earn in, opting in so you can claim, what a referred swap pays you, and claiming.
Every group is simulated first. Nothing is signed or sent without --send.

    Needs py-algorand-sdk.
    (Load your 25 words into PLATFORM_MNEMONIC first: docs/GETTING-STARTED.md, step 5. Never type them
    on the command line, where they'd land in your shell history.)
    PLATFORM_ADDRESS=YOUR_ADDRESS python examples/referral_platform.py       # look only
    python examples/referral_platform.py --send      # do it

Optional: ASSETS (comma-separated ids to open, default ALGO,USDC,HOG), FEE_PPM (default 5000),
ALGOD_URL, ALGOD_TOKEN.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from algosdk import account, encoding, mnemonic, transaction  # noqa: E402
from algosdk.v2client import algod as algod_client  # noqa: E402
from algosdk.v2client.models import SimulateRequest, SimulateRequestTransactionGroup  # noqa: E402

from hogswap_v3 import ALGO, HOG, USDC, Algod, HogswapClient, format_units, group_base64, sign_transactions  # noqa: E402

send = "--send" in sys.argv
key = mnemonic.to_private_key(os.environ["PLATFORM_MNEMONIC"]) if os.environ.get("PLATFORM_MNEMONIC") else None
referrer = account.address_from_private_key(key) if key else os.environ.get("PLATFORM_ADDRESS")
if not referrer:
    sys.exit("set PLATFORM_ADDRESS (look only) or PLATFORM_MNEMONIC (to send)")
if send and not key:
    sys.exit("--send needs PLATFORM_MNEMONIC")

url = os.environ.get("ALGOD_URL", "https://mainnet-api.algonode.cloud")
token = os.environ.get("ALGOD_TOKEN", "")
node = algod_client.AlgodClient(token, url)
algod = Algod(url, token=token or None)
hogswap = HogswapClient()
wanted = [int(a) for a in os.environ["ASSETS"].split(",")] if os.environ.get("ASSETS") else [ALGO, USDC, HOG]
fee_ppm = int(os.environ.get("FEE_PPM", "5000"))


def to_txns(group):
    return [encoding.msgpack_decode(b) for b in group_base64(group)]


def simulate(groups):
    """Simulate each group against current chain state (algod takes one group per request); stop
    on the first failure. Each is checked on its own, so a later group can't rely on an earlier one."""
    for i, txns in enumerate(groups):
        req = SimulateRequest(
            txn_groups=[SimulateRequestTransactionGroup(txns=[transaction.SignedTransaction(t, None) for t in txns])],
            allow_empty_signatures=True,
        )
        g = node.simulate_transactions(req)["txn-groups"][0]
        if g.get("failure-message"):
            sys.exit(f"group {i + 1} of {len(groups)} would fail at {g.get('failed-at')}: {g['failure-message']}")
    if groups:
        print(f"  simulated {len(groups)} group(s): clean")


def run(label, groups):
    simulate(groups)
    if not send:
        return
    for i, txns in enumerate(groups):
        res = algod.submit_and_confirm(sign_transactions(txns, {referrer: key}))
        print(f"  {label} {i + 1}/{len(groups)} confirmed in round {res['confirmed_round']}: {res['tx_id']}")


# 1. Where do we stand?
status = hogswap.referrer_status(referrer)
print(f"platform {referrer}")
print(f"discount token: {status['discount_token_id'] or 'off'}; open assets: {len(status['assets'])}")
for a in status["assets"]:
    print(f"  asset {a['asset_id']}: accrued {a['accrued']} base units{'' if a['can_receive'] else ' (opt in to claim)'}")

# 2. Open the assets you want to earn in. Only the ones not open yet produce transactions.
setup = hogswap.referrer_setup(referrer, assets=wanted)
print(f"\nopen {', '.join(map(str, wanted))}: {len(setup['groups'])} group(s) to sign")
for g in setup["groups"]:
    print(f"  {'; '.join(g['steps'])}; deposit {format_units(g['deposit_microalgo'], 6)} ALGO, fee {format_units(g['network_fee_microalgo'], 6)} ALGO")
for n in setup["notes"]:
    print("  note:", n)
run("setup", [to_txns(g) for g in setup["groups"]])

# 3. Opt in to each asset (not ALGO) you don't hold yet, or its claims can't pay you.
held = {a["asset-id"] for a in node.account_info(referrer).get("assets", [])}
missing = [a for a in wanted if a != 0 and a not in held]
print(f"\nopt-ins needed: {', '.join(map(str, missing)) if missing else 'none'}")
if missing:
    sp = node.suggested_params()
    run("opt-in", [[transaction.AssetTransferTxn(referrer, sp, referrer, 0, a)] for a in missing])

# 4. What one referred swap pays: 100 ALGO -> USDC at your rate.
q = hogswap.quote(asset_in=ALGO, asset_out=USDC, amount_in=100_000_000, referrer=referrer, fee_ppm=fee_ppm)
print(f"\na 100 ALGO -> USDC swap you refer at {fee_ppm} ppm:")
print(f"  user receives about {format_units(q['expected_out'], 6)} USDC, paying {q['router_fee_ppm_effective']} ppm in fees")
print(f"  you earn {format_units(q['referrer_fee_amount'], 6)} USDC ({q['referrer_share_ppm']} ppm of the output)")

# 5. Claim whatever has accrued.
claim = hogswap.referrer_claim(referrer)
print(f"\nclaim: {len(claim['groups'])} group(s)")
for n in claim["notes"]:
    print("  note:", n)
run("claim", [to_txns(g) for g in claim["groups"]])

if not send:
    print("\nlook-only run: nothing was signed or sent. Add --send (with PLATFORM_MNEMONIC) to do it.")
