# Examples

| File | What it shows | Signs or sends? |
|---|---|---|
| `quote.py` | A quote, with amounts converted exactly | No |
| `find_asset.py` | Look up asset ids by name | No |
| `referral_platform.py` | A platform's referral flow start to finish: status, opening assets, opt-ins, what a referred swap pays, claiming; simulates every group | Only with `--send` |
| `lp.py` | LP deposit (two-sided, one-sided) and withdraw quotes on a STAMM pool | No |
| `my_swap.py` | Swap from your own account: shows the quote, asks before sending | **Yes**, after you answer `y` (or with `--yes`) |
| `compose_before_swap.py` | Your own payment in the same atomic group, before the swap | Only with `--send` |
| `after_swap.py` | Use the swap's output in the same atomic group, sized to the guaranteed minimum; simulates first | Only with `--send` |
| `bot_sign.py` | A backend that quotes, builds, signs with its own key and submits | **Yes**, a real mainnet swap (`DRY_RUN=1` stops before signing) |

Run them from the repo root, e.g. `python examples/quote.py 25`.
