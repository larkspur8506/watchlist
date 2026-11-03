# -*- coding: utf-8 -*-
"""行情源适配层：纯解析函数 + 抓取函数。

设计纪律：
- 解析函数只吃「原始文本/字典」，不碰网络 —— 这样单测可以钉死字段错位。
- 抓取失败只返回空，绝不伪造 0.00%（会把「没数据」读成「平盘」）。
- 每个源的字段位置都是实测出来的，改之前先看 tests/test_sources.py 里的真实样本。
"""
import json
import re
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
SINA_REFERER = "https://finance.sina.com.cn"


def _http(url, headers=None, timeout=8):
    h = {"User-Agent": UA}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _gbk(b):
    return b.decode("gbk", errors="replace")


def _f(x):
    try:
        return float(str(x).replace(",", "").strip())
    except Exception:
        return None


# ---------- 腾讯（美股 / 港股 / A股 / 指数） ----------
# 各市场的字段偏移不一样（美股时间在 31、A股在 30，中间空位数量不同），所以不写死下标：
# 先用正则定位「时间戳」字段，其后紧邻两位就是 涨跌额、涨跌幅%。三个市场共用一套逻辑。
TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}|\d{14}|\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})$")


def parse_tencent(text):
    out = {}
    for line in text.splitlines():
        m = re.match(r'v_(\w+)="(.*)";?\s*$', line.strip())
        if not m:
            continue
        key = m.group(1)
        parts = m.group(2).split("~")
        ti = next((i for i, v in enumerate(parts) if TS_RE.match(v.strip())), None)
        if ti is None or len(parts) < ti + 3:
            continue
        price, prev = _f(parts[3]), _f(parts[4])
        chg, pct = _f(parts[ti + 1]), _f(parts[ti + 2])
        if price is None or pct is None:
            continue
        # 腾讯的美股代码形如 SCHD.AM / AVGE.AM；A股/指数是纯数字
        sym = parts[2].split(".")[0] if parts[2] else key
        out[sym.upper()] = {
            "price": price, "prev_close": prev, "chg": chg, "chg_pct": pct,
            "ts": parts[ti], "name": parts[1],
        }
    return out


def fetch_tencent(symbols):
    if not symbols:
        return {}
    q = ",".join("us" + s for s in symbols)
    return parse_tencent(_gbk(_http("https://qt.gtimg.cn/q=" + q)))


# ---------- 新浪美股 ----------
# 逗号分隔（0 起）：0=代码 1=现价 2=涨跌幅% 3=时间 4=涨跌额 5=开盘 6=最高 7=最低
# 25/26=盘前盘后时间戳（串里自带，页面用它判断是不是延长时段）
def parse_sina_us(text):
    out = {}
    for line in text.splitlines():
        m = re.match(r'var hq_str_gb_(\w+)="(.*)";?\s*$', line.strip())
        if not m:
            continue
        sym = m.group(1).upper()
        parts = m.group(2).split(",")
        if len(parts) < 5:
            continue
        price, pct, chg = _f(parts[1]), _f(parts[2]), _f(parts[4])
        if price is None or pct is None:
            continue
        out[sym] = {"price": price, "prev_close": None, "chg": chg, "chg_pct": pct,
                    "ts": parts[3], "name": parts[0] if len(parts[0]) < 2 else ""}
    return out


def fetch_sina_us(symbols):
    if not symbols:
        return {}
    q = ",".join("gb_" + s.lower() for s in symbols)
    return parse_sina_us(_gbk(_http("https://hq.sinajs.cn/list=" + q,
                                    headers={"Referer": SINA_REFERER})))


# ---------- 新浪伦敦 ----------
# 实测字段（0 起）：0=代码 1=昨收 2=最高 3=开盘 4=最低 5=现价 6=成交量 7=成交额 8=时间
# 校准方法：现价必须落在 [最低, 最高] 之间，且 昨收 与 现价 同量级（IITU 用便士、VUAG 用英镑）。
def parse_sina_lse(text):
    out = {}
    for line in text.splitlines():
        m = re.match(r'var hq_str_lse_(\w+)="(.*)";?\s*$', line.strip())
        if not m:
            continue
        parts = m.group(2).split(",")
        if len(parts) < 6:
            continue
        prev, high, _open, low, last = (_f(parts[1]), _f(parts[2]), _f(parts[3]),
                                        _f(parts[4]), _f(parts[5]))
        if not last or not prev:
            continue
        if low is not None and high is not None and not (low <= last <= high):
            continue  # 字段错位时不猜，宁可这一行 stale
        out[m.group(1).upper()] = {
            "price": last, "prev_close": prev, "chg": round(last - prev, 4),
            "chg_pct": round((last / prev - 1) * 100, 2), "ts": parts[8] if len(parts) > 8 else "",
            "name": "",
        }
    return out


def fetch_sina_lse(symbols):
    if not symbols:
        return {}
    q = ",".join("lse_" + s.lower() for s in symbols)
    return parse_sina_lse(_gbk(_http("https://hq.sinajs.cn/list=" + q,
                                     headers={"Referer": SINA_REFERER})))


# ---------- BTC ----------
# oracle1 在新加坡/美国区域，api.binance.com 直接返回 451「restricted location」；
# data-api.binance.vision 是官方公开行情镜像，同一份数据、不挑地区，故做首选。
BTC_HOSTS = ("https://data-api.binance.vision", "https://api.binance.com")


def parse_binance(d):
    return {"price": _f(d.get("lastPrice")), "prev_close": _f(d.get("prevClosePrice")),
            "chg": _f(d.get("priceChange")), "chg_pct": _f(d.get("priceChangePercent")),
            "ts": "", "name": "Bitcoin"}


def fetch_btc():
    last_err = None
    for host in BTC_HOSTS:
        try:
            d = json.loads(_http(host + "/api/v3/ticker/24hr?symbol=BTCUSDT"))
            q = parse_binance(d)
            if q["price"]:
                return {"BTC": q}
        except Exception as e:  # 451 是地区限制，换镜像继续
            last_err = e
    if last_err:
        raise last_err
    return {}


# ---------- 迷你走势（近 N 个收盘价） ----------
# 腾讯的美股 K 线只返回当天 1 根（实测），所以美股走新浪 JSONP 全历史接口。
def parse_sina_dailyk(text, n=20):
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return []
    try:
        rows = json.loads(m.group(0))
    except Exception:
        return []
    closes = [(_f(r.get("c"))) for r in rows if isinstance(r, dict)]
    return [c for c in closes if c is not None][-n:]


def fetch_spark_us(sym, n=20):
    # 注意：URL 里有 %20（JSONP 回调名里的空格），绝不能对整条字符串做 % 格式化，
    # 否则 %2 会被当成格式符吃掉（踩过一次）。
    url = ("https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20k/"
           "US_MinKService.getDailyK?symbol=" + sym.upper())
    return parse_sina_dailyk(_gbk(_http(url, headers={"Referer": SINA_REFERER}, timeout=10)), n)


def fetch_spark_tencent(code, n=20):
    """code 形如 sz399006 —— 腾讯 A股/指数日线（只有 A 股市场可用）。"""
    url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=%s,day,,,%d,qfq" % (code, n))
    d = json.loads(_http(url))
    for k in ("day", "qfqday"):
        rows = (d.get("data", {}).get(code, {}) or {}).get(k) or []
        if rows:
            return [_f(r[2]) for r in rows if len(r) > 2 and _f(r[2]) is not None][-n:]
    return []


def fetch_spark_crypto(sym="BTCUSDT", n=20):
    """Binance 日线收盘（加密货币唯一在用的走势源）；同 fetch_btc 走 .vision 镜像。"""
    for host in BTC_HOSTS:
        try:
            d = json.loads(_http("%s/api/v3/klines?symbol=%s&interval=1d&limit=%d"
                                 % (host, sym, n)))
            out = [_f(r[4]) for r in d if len(r) > 4 and _f(r[4]) is not None]
            if out:
                return out
        except Exception:
            continue
    return []
