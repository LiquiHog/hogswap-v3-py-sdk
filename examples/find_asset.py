"""Look up asset ids by name or unit name. Nothing is signed or sent.

    python examples/find_asset.py gold
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hogswap_v3 import HogswapClient  # noqa: E402

q = " ".join(sys.argv[1:])
if not q:
    sys.exit("usage: python examples/find_asset.py <name or unit name>")
assets = HogswapClient().assets(q=q, limit=20)["assets"]
if not assets:
    print(f'nothing found for "{q}"')
for a in assets:
    print(f"{a['asset_id']:>12}  {(a.get('unit_name') or ''):<10} {a.get('name') or ''} ({a['decimals']} decimals)")
print("\nALGO is asset 0. Check the id in your wallet or an explorer before trading: names can be copied.")
