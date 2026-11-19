"""Constants for the public HogSwap v3 API and router."""

DEFAULT_BASE_URL = "https://hogswap-v3.liquihog.dev"

#: The HogSwap v3 router application on Algorand mainnet.
ROUTER_APP_ID = 3687031461

#: Well-known asset ids (mainnet). ALGO is asset 0 throughout the API.
ALGO = 0
USDC = 31566704
HOG = 3178895177

#: The router's base fee in parts per million of the swap output (0.05%).
BASE_FEE_PPM = 500

#: The highest rate a referring platform can set, in ppm (1%).
FEE_PPM_CAP = 10_000

#: Public limits per client IP. Quote, execute and the referrer endpoints share one window:
#: 30 requests per 10 seconds, at most 4 running at once. Market data reads are not limited.
RATE_LIMIT_PER_WINDOW = 30
RATE_LIMIT_WINDOW_S = 10.0
RATE_LIMIT_IN_FLIGHT = 4

#: A quote can be built for about 30 seconds, at most 5 times.
QUOTE_TTL_S = 30
BUILDS_PER_QUOTE = 5

#: Venue keys for ``exclude_venues``, with what each covers.
VENUES = {
    "stamm": "STAMM pools (all fee tiers)",
    "tinyman_v2": "Tinyman v2",
    "pact_cp": "Pact constant-product pools (v1 and v2)",
    "pact_stable": "Pact stableswap pools",
    "pact_weighted": "Pact weighted pools",
    "pact_clmm": "Pact concentrated-liquidity pools",
    "algofi_cp": "AlgoFi constant-product pools",
    "humble_v2": "Humble v2",
    "biatec": "Biatec concentrated-liquidity pools",
    "folks_lend": "Folks Finance lending (deposit and withdraw fAssets)",
    "xalgo": "xALGO liquid staking (mint and burn)",
    "talgo": "tALGO liquid staking (mint and burn)",
    "dualstake": "DualSTAKE liquid staking (mint and redeem)",
}

#: The most transactions an Algorand atomic group can hold.
MAX_GROUP_SIZE = 16

#: The most asset ids one referrer_setup or referrer_claim request takes.
MAX_REFERRER_ASSETS = 200
