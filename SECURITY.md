# Security policy

## Reporting a vulnerability

If you find a security issue in this SDK, the HogSwap API, or the router contract, please email
**liquihog@gmail.com** with steps to reproduce. Please don't open a public issue for anything
exploitable before it has been fixed.

## How the SDK is built

- **It never sends or stores keys.** It requests quotes and receives unsigned transactions.
  Signing happens in your user's wallet, or locally in your own process if you use
  `sign_group` / `sign_transactions`, and submission goes to the algod node you choose.
- **The router contract enforces the trade.** Every group is atomic, and delivery below the
  quote's `min_out_at_slippage` reverts the whole group.
- **No required dependencies.** `py-algorand-sdk` is needed only for the helpers that decode or
  sign transactions (`sign_group`, `sign_transactions`, `compose_group`, `final_txid`).
- **API keys, if you have one, belong on a server.** Never put one in browser code; public
  browser use needs no key.
