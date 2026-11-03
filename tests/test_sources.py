# -*- coding: utf-8 -*-
"""解析层单测：样本全部是实测抓到的原始响应（截断到必要字段）。"""
import json
import unittest
import urllib.error

from app import sources


TENCENT_US = ('v_usSCHD="200~红利股ETF-Schwab~SCHD.AM~35.90~35.78~35.78~27008177~0~0~35.95~900~'
              '0~0~0~0~0~0~0~0~0~35.96~2600~0~0~0~0~0~0~0~0~~2026-11-02 16:00:01~0.12~0.34~'
              '35.99~35.78~USD~27008177~970349624~~~~~~0.59~~~Schwab Stra";')

TENCENT_INDEX = ('v_sz399006="' + "~".join(
    ["51", "创业板指", "399006", "2435.60", "2458.70", "2429.77", "109505042"]
    + ["0"] * 22 + ["", "20261103120515", "-23.10", "-0.94", "2471.90", "2406.64"]) + '";')

SINA_US = ('var hq_str_gb_schd="Schwab美国红利股指数ETF,35.9000,0.34,2026-11-03 09:46:31,0.1200,'
           '35.7800,35.9900,35.7800,38.0000,30.0000,27008177,0,0,0.00,--,0.00,0.59,0.34,0.00,0,0,'
           '0.0000,0.00,0.00,Nov 02 07:30PM EST,Nov 02 04:00PM EST,35.7800,168,1,2026";')

SINA_US_EMPTY = 'var hq_str_gb_iitu="";'

SINA_LSE = ('var hq_str_lse_iitu="iitu,3721,3765,3755,3713,3733,315135,282940229,'
            '2026-11-02 16:35:11,3700,50,3722,2042,120,2,16:35:06.881,,1";\n'
            'var hq_str_lse_vuag="vuag,110.1,110.78,109.84,109.52,109.78,450883,9847215,'
            '2026-11-02 16:35:17,109.9,3,110.18,601,120,2,16:35:09.482,,1";')

SINA_DAILYK = ('/*<script>location.href=\'//sina.com\';</script>*/\nvar k([{"d":"2026-10-29",'
               '"o":"35.50","h":"35.80","l":"35.40","c":"35.70","v":"1","a":"0"},'
               '{"d":"2026-10-30","o":"35.70","h":"35.90","l":"35.60","c":"35.78","v":"1","a":"0"},'
               '{"d":"2026-11-02","o":"35.78","h":"35.99","l":"35.78","c":"35.90","v":"1","a":"0"}]);')


class TestTencent(unittest.TestCase):
    def test_us_fields(self):
        q = sources.parse_tencent(TENCENT_US)["SCHD"]
        self.assertEqual(q["price"], 35.90)
        self.assertEqual(q["prev_close"], 35.78)
        self.assertAlmostEqual(q["chg_pct"], 0.34)
        self.assertIn("2026-11-02", q["ts"])

    def test_a_share_index_layout_same_offsets(self):
        q = sources.parse_tencent(TENCENT_INDEX)["399006"]
        self.assertEqual(q["price"], 2435.60)
        self.assertAlmostEqual(q["chg_pct"], -0.94)
        self.assertEqual(q["chg"], -23.10)


class TestSinaUS(unittest.TestCase):
    def test_fields(self):
        q = sources.parse_sina_us(SINA_US)["SCHD"]
        self.assertEqual(q["price"], 35.90)
        self.assertAlmostEqual(q["chg_pct"], 0.34)
        self.assertAlmostEqual(q["chg"], 0.12)
        self.assertIn("2026-11-03", q["ts"])

    def test_empty_symbol_is_skipped_not_zero(self):
        self.assertEqual(sources.parse_sina_us(SINA_US_EMPTY), {})


class TestSinaLSE(unittest.TestCase):
    def test_pence_and_pounds_units(self):
        # 期望值用 Wealthfolio 的日收盘对账过：IITU 11-02 收 3721p、10-30 收 3733p；
        # VUAG 11-02 收 110.10 GBP、10-30 收 109.78 GBP。涨跌方向不能反。
        q = sources.parse_sina_lse(SINA_LSE)
        self.assertEqual(q["IITU"]["price"], 3721)        # 便士
        self.assertEqual(q["VUAG"]["price"], 110.10)      # 英镑
        self.assertAlmostEqual(q["IITU"]["chg_pct"], round((3721 / 3733 - 1) * 100, 2))
        self.assertAlmostEqual(q["VUAG"]["chg_pct"], round((110.10 / 109.78 - 1) * 100, 2))
        self.assertLess(q["IITU"]["chg_pct"], 0)          # IITU 当期是跌的，符号钉死

    def test_out_of_range_row_is_dropped(self):
        # 现价 150 落在 [99,101] 之外 = 字段错位，必须整行丢弃而不是硬算
        bad = 'var hq_str_lse_xxx="xxx,150,101,100,99,120,0,0,2026-11-02 16:00:00";'
        self.assertEqual(sources.parse_sina_lse(bad), {})


class TestSpark(unittest.TestCase):
    def test_daily_k_closes(self):
        self.assertEqual(sources.parse_sina_dailyk(SINA_DAILYK), [35.70, 35.78, 35.90])

    def test_garbage_returns_empty(self):
        self.assertEqual(sources.parse_sina_dailyk("not json"), [])

    def test_url_keeps_jsonp_percent_encoding(self):
        """回归：URL 里的 %20 曾被 % 格式化吃掉并抛 ValueError（spark 全空）。"""
        seen = {}

        def fake_http(url, headers=None, timeout=8):
            seen["url"] = url
            return SINA_DAILYK.encode("utf-8")

        old = sources._http
        sources._http = fake_http
        try:
            out = sources.fetch_spark_us("schd")
        finally:
            sources._http = old
        self.assertEqual(len(out), 3)
        self.assertIn("var%20k/", seen["url"])
        self.assertTrue(seen["url"].endswith("symbol=SCHD"))


class TestBinance(unittest.TestCase):
    def test_parse(self):
        q = sources.parse_binance({"lastPrice": "77051.38", "prevClosePrice": "78522.0",
                                   "priceChange": "-1470.62", "priceChangePercent": "-1.873"})
        self.assertEqual(q["price"], 77051.38)
        self.assertAlmostEqual(q["chg_pct"], -1.873)

    def test_geo_blocked_host_falls_back_to_mirror(self):
        """回归：oracle1 上 api.binance.com 返回 451，必须能自动换 .vision 镜像。"""
        seen = []

        def fake_http(url, headers=None, timeout=8):
            seen.append(url)
            if "data-api.binance.vision" not in url:
                raise urllib.error.HTTPError(url, 451, "restricted location", {}, None)
            return json.dumps({"lastPrice": "77000", "prevClosePrice": "78000",
                               "priceChange": "-1000", "priceChangePercent": "-1.28"}).encode()

        old = sources._http
        sources._http = fake_http
        try:
            q = sources.fetch_crypto({"BTC": "BTCUSDT"})
        finally:
            sources._http = old
        self.assertEqual(q["BTC"]["price"], 77000.0)
        self.assertIn("data-api.binance.vision", seen[0])  # 首选镜像，一次就成功


class TestSparkLSE(unittest.TestCase):
    """LSE 迷你线来自 Wealthfolio 的 quotes 表（临时库造数据，不依赖真库）。"""

    def _make_db(self, tmpdir):
        import os, sqlite3
        db = os.path.join(tmpdir, "wf.db")
        con = sqlite3.connect(db)
        con.executescript("""
            create table assets (id text, display_code text);
            create table quotes (asset_id text, day text, close text);
            insert into assets values ('a1','IITU');
            insert into quotes values ('a1','2026-10-28','3947');
            insert into quotes values ('a1','2026-10-29','3898');
            insert into quotes values ('a1','2026-11-02','3721');
        """)
        con.commit(); con.close()
        return db

    def test_reads_daily_closes_in_ascending_order(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            db = self._make_db(d)
            self.assertEqual(sources.fetch_spark_lse("IITU", 20, db=db), [3947.0, 3898.0, 3721.0])

    def test_missing_db_returns_empty_not_raise(self):
        self.assertEqual(sources.fetch_spark_lse("IITU", 20, db="/nonexistent/wf.db"), [])

    def test_stale_wf_data_hides_the_line(self):
        """WF 停更时不能拿旧线冒充新线：最后一根超过 5 个自然日就返回空。"""
        import os, sqlite3, tempfile
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "wf.db")
            con = sqlite3.connect(db)
            con.executescript("""
                create table assets (id text, display_code text);
                create table quotes (asset_id text, day text, close text);
                insert into assets values ('a1','IITU');
                insert into quotes values ('a1','2026-01-05','3500');
                insert into quotes values ('a1','2026-01-06','3510');
            """)
            con.commit(); con.close()
            self.assertEqual(sources.fetch_spark_lse("IITU", 20, db=db), [])


if __name__ == "__main__":
    unittest.main()
