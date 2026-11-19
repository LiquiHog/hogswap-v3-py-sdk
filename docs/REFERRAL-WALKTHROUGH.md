# Referral walkthrough: from nothing to your first claim

This takes a wallet, site or bot from zero to earning on the swaps it sends through HogSwap, and
claiming those earnings. [REFERRALS.md](REFERRALS.md) is the reference for the terms and every
option; this is the order to do things in.

**By the end** your platform account will be set up to earn in the assets you choose. Your swaps
will carry your address and rate, and you'll have checked a balance and claimed it.

Nothing here needs approval or a sign-up. Every step returns unsigned transactions that only your
platform account signs.

## 1. Pick a platform account and fund it

Use an account dedicated to the programme: earnings arrive in it, and it signs the setup and claim
transactions. A team multisig or a backend-held key both work.

Fund it with ALGO for:

| What | How much |
|---|---|
| Opening each asset | 0.0225 ALGO, refunded when you close it; plus 0.0097 (not refunded) if you're the first platform to open that asset |
| Opting in to each asset you earn in, except ALGO (minimum balance, returned on opt-out) | 0.1 ALGO |
| Network fees | 0.001 ALGO per transaction: about 0.016 ALGO for a full setup group of ~50 assets (0.002 for a few), and about 0.0015 ALGO per asset claimed |

For example, earning in ALGO, USDC and eight other tokens comes to under 0.33 ALGO in deposits and
0.9 ALGO in opt-ins. Funding 2 ALGO leaves room for fees.

## 2. Choose the assets you earn in

You earn in each swap's **output** asset, the one your users receive. So open the assets your
users buy most: usually ALGO, USDC, and the tokens your platform features.

- **Until an asset is open,** your share of swaps paying out in it goes to the router. The swap
  itself always completes.
- **You can open more later.** It only takes a few transactions.
- **Up to 200 assets per request.** About 50 fit in one signed group, so even 200 assets take
  only about four signatures.

## 3. Look before you sign

The example walks the whole flow and simulates every group without sending anything (it needs
py-algorand-sdk):

```sh
PLATFORM_ADDRESS=YOUR_PLATFORM_ADDRESS ASSETS=0,31566704,3178895177 python examples/referral_platform.py
```

```text
platform YOUR_PLATFORM_ADDRESS
discount token: off; open assets: 0

open 0, 31566704, 3178895177: 1 group(s) to sign
  open 3 assets [0, 31566704, 3178895177] (deposit 67500 µALGO); deposit 0.0675 ALGO, fee 0.002 ALGO
  simulated 1 group(s): clean

opt-ins needed: 3178895177
  simulated 1 group(s): clean

a 100 ALGO -> USDC swap you refer at 5000 ppm:
  user receives about 7.58608 USDC, paying 5000 ppm in fees
  you earn 0.017154 USDC (2250 ppm of the output)
```

If a group would fail, the example says which one and why, before anything is signed.

## 4. Open the assets

**From a script:** run the same example with the platform's 25 words in `PLATFORM_MNEMONIC` and
`--send`. It simulates again, then signs and submits each group in order.

**From your backend:**

```python
from hogswap_v3 import Algod, HogswapClient, sign_group

hogswap = HogswapClient()
algod = Algod("https://mainnet-api.algonode.cloud")
setup = hogswap.referrer_setup(PLATFORM, assets=[0, 31566704, 3178895177])

for g in setup["groups"]:
    print(g["steps"], g["deposit_microalgo"])            # what is being signed
    algod.submit_and_confirm(sign_group(g, platform_key))  # in order, one group at a time
```

If the platform signs in a browser wallet instead, send each group's `unsigned_group` to the
frontend and have the wallet sign it (see [COMPOSING.md](COMPOSING.md#mixed-signers)).

Only assets not open yet produce transactions, so running setup again is harmless.

## 5. Opt in to the same assets

A claim pays out by plain transfer, so the platform account must hold each asset (ALGO aside). In
a wallet app, use **Add asset**. From code, it's a zero-amount transfer to yourself; see
[PERSONAL-USE.md](PERSONAL-USE.md#opt-ins). The example's `--send` run does it for you.

You can opt in any time before you claim. Earnings accrue either way.

## 6. Put your address and rate on every swap

```python
quote = hogswap.quote(
    asset_in=asset_in, asset_out=asset_out, amount_in=amount_in, sender=user,
    referrer=PLATFORM,
    fee_ppm=5000,  # 0.5%; up to 10000 (1%)
)
```

Then `execute()`, sign and submit as usual. The user signs the swap; your platform account
signs nothing here.

- **You keep half of the fee above the 0.05% base.** At 5000 ppm (0.5%), you earn 0.225% of
  each swap's output.
- **Show users the fee.** `quote["router_fee_ppm_effective"]` is the rate they pay (holders of
  your discount token, if you set one, pay less: quotes don't model it).
  `quote["expected_out"]` already has it taken out.
- **Plain swaps only.** LP, multi-input, basket and cover-fee quotes can't carry a referrer; the
  SDK refuses them before sending.

## 7. Check that it's working

After your first referred swap confirms:

```python
status = hogswap.referrer_status(PLATFORM)
# status["assets"]: [{"asset_id", "accrued", "can_receive"}]
```

`accrued` is in the asset's base units, as a decimal string. Status is cached for 10 seconds.

- **The balance didn't move?** Check that the swap's output asset is open (it's in
  `status["assets"]`), and that the quote carried your `referrer`.
- **Every swap also emits an event:** `ReferrerAccrued` when you were credited, `ReferrerUnpaid`
  when the asset wasn't open.

## 8. Claim

```python
claim = hogswap.referrer_claim(PLATFORM)  # every asset with a balance
for g in claim["groups"]:
    algod.submit_and_confirm(sign_group(g, platform_key))
```

- **Claim when it's worth it.** Each asset claimed costs about 0.0015 ALGO in fees (two assets
  in one group: 0.003 ALGO), and each group shows its exact `network_fee_microalgo`.
- **`claim["notes"]` explains anything skipped:** nothing accrued, not opted in, not open.
- **Only your account can claim your balance,** and the router's owner can't touch it.

## 9. Optional: a discount token

Holders of a token you choose can pay a lower rate. Set it with
`referrer_setup(referrer, discount_token_id=..., discount_unit=...)`. It takes a 0.0225 ALGO
deposit the first time, and changing it later is free. It lowers your earnings and the router's
equally, so only set one if you want to reward holders. See
[REFERRALS.md](REFERRALS.md#discount-token-optional).

## 10. If you stop

`referrer_claim(referrer, close=True, unregister=True)` pays out everything and refunds
every 0.0225 ALGO deposit. Opt in to every asset with a balance first, or it's skipped. Section 4
of [REFERRALS.md](REFERRALS.md) explains the options.

## Checklist

- [ ] Platform account funded (step 1)
- [ ] Assets chosen and opened (steps 2 to 4)
- [ ] Platform account opted in to them (step 5)
- [ ] `referrer` and `fee_ppm` on every quote, fee shown to users (step 6)
- [ ] A referred swap shows up in `referrer_status` (step 7)
- [ ] A claim schedule (step 8)
