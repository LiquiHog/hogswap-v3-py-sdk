import asyncio
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hogswap_v3 import (  # noqa: E402
    AsyncHogswapClient,
    HogswapBuildError,
    HogswapClient,
    HogswapInputError,
    HogswapMissingOptInError,
    HogswapNoRouteError,
    HogswapQuoteExpiredError,
    HogswapRateLimitError,
    RateLimiter,
    apply_slippage,
    assert_fully_signed,
    format_units,
    group_base64,
    group_bytes,
    parse_units,
    to_amount_str,
    to_int,
)

ADDR = "AEBAGBAFAYDQQCIKBMGA2DQPCAIREEYUCULBOGAZDINRYHI6D4QDTYK3BA"
BIG = "18446744073709551615"


class FakeTransport:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": headers, "body": None if body is None else json.loads(body)})
        status, hdrs, payload = self.replies.pop(0) if self.replies else (200, {}, {})
        return status, hdrs, json.dumps(payload).encode() if not isinstance(payload, bytes) else payload


def client(replies, **kw):
    t = FakeTransport(replies)
    kw.setdefault("rate_limit", False)
    kw.setdefault("retries", 0)
    return HogswapClient(transport=t, **kw), t


class Amounts(unittest.TestCase):
    def test_request_amounts_are_exact_strings(self):
        self.assertEqual(to_amount_str(1500000), "1500000")
        self.assertEqual(to_amount_str(" 42 "), "42")
        self.assertEqual(to_amount_str(BIG), BIG)
        self.assertEqual(to_amount_str(int(BIG)), BIG)

    def test_lossy_or_invalid_amounts_are_refused(self):
        for bad in (1.5, 1e6, True, -1, "1.5", "1e6", None, str(1 << 64)):
            with self.assertRaises(HogswapInputError, msg=repr(bad)):
                to_amount_str(bad)

    def test_response_amounts(self):
        self.assertEqual(to_int(BIG), (1 << 64) - 1)
        self.assertIsNone(to_int(None))
        with self.assertRaises(HogswapInputError):
            to_int("abc")

    def test_format_and_parse_units(self):
        self.assertEqual(format_units(1234567, 6), "1.234567")
        self.assertEqual(format_units("5000000", 6), "5")
        self.assertEqual(format_units(BIG, 6), "18446744073709.551615")
        self.assertEqual(format_units(1999999, 6, max_decimals=2), "1.99")
        self.assertEqual(parse_units("1.5", 6), 1500000)
        self.assertEqual(parse_units("18446744073709.551615", 6), int(BIG))
        with self.assertRaises(HogswapInputError):
            parse_units("0.0000001", 6)
        for s in ("0", "1", "0.1", "123456.654321"):
            self.assertEqual(format_units(parse_units(s, 6), 6), s)
        self.assertEqual(apply_slippage(999, 50), 994)


class Requests(unittest.TestCase):
    def test_quote_body(self):
        c, t = client([(200, {}, {"quote_id": "q1"})])
        self.assertEqual(c.quote(asset_in=0, asset_out=31566704, amount_in=10_000_000, slippage_bps=30, sender=ADDR)["quote_id"], "q1")
        self.assertEqual(t.calls[0]["url"], "https://hogswap-v3.liquihog.dev/quote")
        self.assertEqual(t.calls[0]["body"], {"asset_out": 31566704, "asset_in": 0, "amount_in": "10000000", "slippage_bps": 30, "sender": ADDR})

    def test_referred_quote_and_rules(self):
        c, t = client([(200, {}, {})])
        c.quote(asset_in=0, asset_out=31566704, amount_in="1000000", referrer=ADDR, fee_ppm=5000)
        self.assertEqual(t.calls[0]["body"], {"asset_out": 31566704, "asset_in": 0, "amount_in": "1000000", "referrer": ADDR, "fee_ppm": 5000})
        for kw in (
            dict(asset_in=0, asset_out=1, amount_in=1, referrer=ADDR, fee_ppm=10001),
            dict(asset_in=0, asset_out=1, amount_in=1, fee_ppm=100),
            dict(asset_in=0, asset_out=1, amount_in=1, referrer=ADDR, cover_algo_fee=True),
            dict(asset_in=0, asset_out=1),
            dict(asset_in=0, asset_out=1, amount_in=1, amount_out=1),
            dict(asset_in=0, asset_out=1, amount_in=0),
            dict(asset_in=0, asset_out=1, amount_in=1.0),
        ):
            with self.assertRaises(HogswapInputError, msg=repr(kw)):
                c.quote(**kw)

    def test_lp_and_basket_bodies(self):
        c, t = client([(200, {}, {})] * 3)
        c.quote(asset_out=0, inputs=[{"asset_id": 31566704, "amount": 1}, {"asset_id": 3178895177, "amount": "2"}])
        c.quote_lp_mint(pool_app_id=3544790053, tier_index=1, amount_a=1000000, amount_b="470000")
        c.quote_lp_redeem(pool_app_id=3544790053, tier_index=1, lp_amount=5, target_asset=0)
        self.assertEqual(t.calls[0]["body"], {"asset_out": 0, "inputs": [{"asset_id": 31566704, "amount": "1"}, {"asset_id": 3178895177, "amount": "2"}]})
        self.assertEqual(t.calls[1]["body"], {"mode": "LP_MINT", "pool_app_id": 3544790053, "tier_index": 1, "amount_a": "1000000", "amount_b": "470000"})
        self.assertEqual(t.calls[2]["body"], {"mode": "LP_REDEEM", "pool_app_id": 3544790053, "lp_amount": "5", "tier_index": 1, "target_asset": 0})

    def test_referrer_calls(self):
        c, t = client([(200, {}, {})] * 4)
        c.referrer_status(ADDR)
        c.referrer_setup(ADDR, assets=[0, 31566704], discount_token_id=3178895177, discount_unit=10**9)
        c.referrer_claim(ADDR, close=True, unregister=True)
        self.assertEqual(t.calls[0]["url"], f"https://hogswap-v3.liquihog.dev/referrer/{ADDR}")
        self.assertEqual(t.calls[1]["body"], {"referrer": ADDR, "assets": [0, 31566704], "discount_token_id": 3178895177, "discount_unit": "1000000000"})
        self.assertEqual(t.calls[2]["body"], {"referrer": ADDR, "close": True, "unregister": True})
        with self.assertRaises(HogswapInputError):
            c.referrer_setup(ADDR)
        with self.assertRaises(HogswapInputError):
            c.referrer_setup(ADDR, discount_token_id=5)
        with self.assertRaises(HogswapInputError):
            c.referrer_setup(ADDR, assets=[0], discount_unit=5)
        many = list(range(1, 202))
        with self.assertRaises(HogswapInputError):
            c.referrer_setup(ADDR, assets=many)
        with self.assertRaises(HogswapInputError):
            c.referrer_claim(ADDR, assets=many)
        c.referrer_setup(ADDR, assets=many[:200])
        self.assertEqual(len(t.calls[3]["body"]["assets"]), 200)

    def test_pagination_and_query(self):
        c, t = client([(200, {}, {"assets": [{"asset_id": 0}], "next_cursor": "0"}), (200, {}, {"assets": [{"asset_id": 1}], "next_cursor": None}), (200, {}, {})])
        self.assertEqual([a["asset_id"] for a in c.iterate_assets(limit=1)], [0, 1])
        self.assertEqual(t.calls[1]["url"], "https://hogswap-v3.liquihog.dev/assets?limit=1&cursor=0")
        c.prices([0, "31566704"])
        self.assertEqual(t.calls[2]["url"], "https://hogswap-v3.liquihog.dev/prices?ids=0%2C31566704")


class Errors(unittest.TestCase):
    def check(self, reply, call, cls, **attrs):
        c, _ = client([reply])
        with self.assertRaises(cls) as cm:
            call(c)
        for k, v in attrs.items():
            self.assertEqual(getattr(cm.exception, k), v)

    def test_mapping(self):
        q = lambda c: c.quote(asset_in=0, asset_out=1, amount_in=1)  # noqa: E731
        e = lambda c: c.execute("q", ADDR)  # noqa: E731
        self.check((404, {}, {"detail": "no route"}), q, HogswapNoRouteError)
        self.check((404, {}, {"detail": "quote_id q not found or expired"}), e, HogswapQuoteExpiredError, code="quote_expired")
        self.check((429, {}, {"detail": "quote_id q exceeded its 5-build budget"}), e, HogswapQuoteExpiredError, code="build_budget_spent")
        self.check((409, {}, {"detail": "build failed: x"}), e, HogswapBuildError)
        self.check((422, {}, {"detail": "not opted in", "error": "missing_opt_in", "assets": [31566704]}), e, HogswapMissingOptInError, assets=[31566704])
        self.check((429, {"Retry-After": "10"}, {"error": "rate limited", "detail": "30 requests/10s per IP"}), q, HogswapRateLimitError, retry_after_s=10.0)

    def test_busy_is_retried(self):
        c, t = client([(503, {"Retry-After": "0"}, {"detail": "router busy"}), (200, {}, {"ok": True})], retries=1)
        self.assertTrue(c.health()["ok"])
        self.assertEqual(len(t.calls), 2)

    def test_execute_not_retried_on_network_error(self):
        n = []

        def broken(*a):
            n.append(1)
            raise OSError("connection reset")

        c = HogswapClient(transport=broken, rate_limit=False, retries=3)
        with self.assertRaises(Exception):
            c.execute("q", ADDR)
        self.assertEqual(len(n), 1)


class Groups(unittest.TestCase):
    def test_group_helpers(self):
        build = {"unsigned_group": [{"txn_b64": "AQID"}, {"txn_b64": "/wA="}]}
        self.assertEqual(group_base64(build), ["AQID", "/wA="])
        self.assertEqual(group_bytes(build), [b"\x01\x02\x03", b"\xff\x00"])
        with self.assertRaises(HogswapInputError):
            assert_fully_signed([b"x", None], 2)
        self.assertEqual(assert_fully_signed([b"x", b"y"], 2), [b"x", b"y"])


class Limiter(unittest.TestCase):
    def test_window(self):
        now = [0.0]
        lim = RateLimiter(2, 1.0, 5, clock=lambda: now[0])
        r1, r2 = lim.acquire(), lim.acquire()
        # A third start must wait for the window: simulate time passing from another thread.
        import threading

        def advance():
            import time

            time.sleep(0.05)
            now[0] = 1.0
            with lim._cond:
                lim._cond.notify_all()

        threading.Thread(target=advance).start()
        r3 = lim.acquire()
        self.assertGreaterEqual(now[0], 1.0)
        for r in (r1, r2, r3):
            r()


class Async(unittest.TestCase):
    def test_async_client(self):
        t = FakeTransport([(200, {}, {"quote_id": "q1"})])
        c = AsyncHogswapClient(transport=t, rate_limit=False)
        q = asyncio.run(c.quote(asset_in=0, asset_out=31566704, amount_in=1))
        self.assertEqual(q["quote_id"], "q1")


class Signing(unittest.TestCase):
    def test_sign_group_with_algosdk(self):
        try:
            from algosdk import account, encoding, transaction
        except ImportError:
            self.skipTest("py-algorand-sdk not installed")
        from hogswap_v3 import sign_group

        sk, addr = account.generate_account()  # a throwaway key, never funded
        sp = transaction.SuggestedParams(fee=1000, first=1, last=1000, gh="wGHE2Pwdvd7S12BL5FaOP20EGYesN73ktiC1qzkkit8=", gen="mainnet-v1.0", flat_fee=True)
        txns = [transaction.PaymentTxn(addr, sp, addr, 0), transaction.PaymentTxn(addr, sp, addr, 1)]
        transaction.assign_group_id(txns)
        build = {"unsigned_group": [{"txn_b64": encoding.msgpack_encode(t)} for t in txns]}
        signed = sign_group(build, sk)
        self.assertEqual(len(signed), 2)
        for raw, t in zip(signed, txns):
            stx = encoding.msgpack_decode(__import__("base64").b64encode(raw).decode())
            self.assertEqual(stx.transaction.get_txid(), t.get_txid())
            self.assertTrue(stx.signature)


    def test_compose_group_puts_yours_first(self):
        try:
            from algosdk import account, encoding, transaction
        except ImportError:
            self.skipTest("py-algorand-sdk not installed")
        from hogswap_v3 import compose_group, sign_transactions

        sk, addr = account.generate_account()
        sp = transaction.SuggestedParams(fee=1000, first=1, last=1000, gh="wGHE2Pwdvd7S12BL5FaOP20EGYesN73ktiC1qzkkit8=", gen="mainnet-v1.0", flat_fee=True)
        swap = [transaction.PaymentTxn(addr, sp, addr, n) for n in (10, 11, 12)]
        transaction.assign_group_id(swap)
        build = {"unsigned_group": [{"txn_b64": encoding.msgpack_encode(t)} for t in swap]}
        mine = [transaction.PaymentTxn(addr, sp, addr, 1)]
        out = compose_group(build, mine)
        self.assertEqual([t.amt for t in out], [1, 10, 11, 12])
        gids = {t.group for t in out}
        self.assertEqual(len(gids), 1)
        self.assertNotEqual(gids.pop(), swap[0].group)
        self.assertEqual(len(sign_transactions(out, {addr: sk})), 4)
        big = {"unsigned_group": [{"txn_b64": encoding.msgpack_encode(transaction.PaymentTxn(addr, sp, addr, n))} for n in range(15)]}
        with self.assertRaises(HogswapInputError):
            compose_group(big, [transaction.PaymentTxn(addr, sp, addr, 1), transaction.PaymentTxn(addr, sp, addr, 2)])
        # after the swap, and both sides together
        later = [transaction.PaymentTxn(addr, sp, addr, 99)]
        self.assertEqual([t.amt for t in compose_group(build, after=later)], [10, 11, 12, 99])
        self.assertEqual([t.amt for t in compose_group(build, mine, later)], [1, 10, 11, 12, 99])
        with self.assertRaises(HogswapInputError):
            compose_group(build)
        with self.assertRaises(HogswapInputError) as cm:
            compose_group(big, after=[transaction.PaymentTxn(addr, sp, addr, 1), transaction.PaymentTxn(addr, sp, addr, 2)])
        self.assertIn("max_outer_txns=14", str(cm.exception))


class AfterSwap(unittest.TestCase):
    def build(self, **extra):
        b = {"quote_id": "q", "unsigned_group": [{"txn_b64": "AQID"}], "notes": []}
        b.update(extra)
        return b

    def test_execute_raises_for_a_failing_group(self):
        c, _ = client([(200, {}, self.build(warnings=[{"code": "missing_opt_in", "detail": "x", "assets": [31566704]}]))])
        with self.assertRaises(HogswapMissingOptInError) as cm:
            c.execute("q", ADDR)
        self.assertEqual(cm.exception.assets, [31566704])
        c, _ = client([(200, {}, self.build(warnings=[{"code": "insufficient_balance", "detail": "x"}]))])
        with self.assertRaises(HogswapBuildError) as cm:
            c.execute("q", ADDR)
        self.assertEqual(cm.exception.code, "insufficient_balance")

    def test_execute_returns_with_allow_warnings_min_out_or_unsimulated_prefix(self):
        w = [{"code": "missing_opt_in", "detail": "x", "assets": [1]}]
        c, _ = client([(200, {}, self.build(warnings=w))])
        self.assertEqual(c.execute("q", ADDR, allow_warnings=True)["warnings"], w)
        c, _ = client([(200, {}, self.build(warnings=w, prefix_simulated=False))])
        self.assertEqual(c.execute("q", ADDR)["quote_id"], "q")
        c, _ = client([(200, {}, self.build(warnings=[{"code": "min_out_risk", "detail": "m"}]))])
        self.assertEqual(c.execute("q", ADDR)["warnings"][0]["code"], "min_out_risk")

    def test_received_from_swap(self):
        from hogswap_v3 import received_from_swap

        class FakeAlgod:
            def wait_for_confirmation(self, tx_id, timeout_s=30.0):
                return {"confirmed-round": 5, "inner-txns": [
                    {"txn": {"txn": {"type": "appl"}}, "inner-txns": [{"txn": {"txn": {"type": "axfer", "arcv": "ROUTER", "aamt": 999, "xaid": 31566704}}}]},
                    {"txn": {"txn": {"type": "axfer", "arcv": ADDR, "aamt": 18446744073709551615, "xaid": 31566704}}},
                    {"txn": {"txn": {"type": "pay", "rcv": ADDR, "amt": 7}}},
                ]}

        self.assertEqual(received_from_swap(FakeAlgod(), "T", ADDR, 31566704), 18446744073709551615)
        self.assertEqual(received_from_swap(FakeAlgod(), "T", ADDR, 0), 7)


if __name__ == "__main__":
    unittest.main()
