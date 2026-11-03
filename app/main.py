# -*- coding: utf-8 -*-
"""watchlist 聚合服务：零依赖（stdlib），对外两个接口 + 一个静态页。

GET /health            无需 token，返回各源最近成功时间，供 1Panel/巡检探活
GET /api/quotes        全量 JSON（缓存，5s 后台刷新；页面无隐私数据，不设口令）
GET /                  单页

纪律：抓取失败保留上一份数值并打 stale=True，绝不给 0.00%（假平盘比没数据更误导）。
"""
import json
import os
import threading
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from . import sources, symbols as cfg

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
REFRESH_S = int(os.environ.get("WATCH_REFRESH_S", "5"))
SPARK_TTL = 600  # 迷你走势 10 分钟刷一次

CACHE = {"items": [], "updated_at": 0, "sources": {}, "sparks": {}}
LOCK = threading.Lock()


def _now_iso(ts=None):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts or time.time()))


def _stamp(key, ok):
    CACHE["sources"][key] = {"ok": ok, "at": _now_iso()}


def _merge(quotes, market):
    """把某一市场的行情合并进 CACHE['items']（保持 symbols 里的顺序）。"""
    for it in CACHE["items"]:
        if it["market"] != market or it["sym"] not in quotes:
            continue
        q = quotes[it["sym"]]
        it.update({k: q[k] for k in ("price", "prev_close", "chg", "chg_pct", "ts") if k in q})
        it["stale"] = False
        it["_seen"] = time.time()


def refresh_once():
    us = [s for s in cfg.all_symbols() if cfg.MARKETS[s][0] == "us"]
    lse = [s for s in cfg.all_symbols() if cfg.MARKETS[s][0] == "lse"]
    try:
        q = sources.fetch_sina_us(us)
        if not q:  # 新浪主源挂了才退腾讯
            q = sources.fetch_tencent(us)
        _stamp("sina_us", bool(q))
        with LOCK:
            _merge(q, "us")
    except Exception:
        _stamp("sina_us", False)
    try:
        q = sources.fetch_sina_lse(lse)
        _stamp("sina_lse", bool(q))
        with LOCK:
            _merge(q, "lse")
    except Exception:
        _stamp("sina_lse", False)
    try:
        q = sources.fetch_crypto(cfg.CRYPTO_PAIRS)
        _stamp("binance", bool(q))
        with LOCK:
            _merge(q, "crypto")
    except Exception:
        _stamp("binance", False)

    now = time.time()
    with LOCK:
        for it in CACHE["items"]:
            if it.get("_seen") and now - it["_seen"] > 60:
                it["stale"] = True
        CACHE["updated_at"] = now


def refresh_sparks():
    while True:
        def one(it):
            try:
                if it["market"] == "us":
                    s = sources.fetch_spark_us(it["sym"])
                elif it["market"] == "crypto":
                    s = sources.fetch_spark_crypto(cfg.CRYPTO_PAIRS[it["sym"]])
                elif it["market"] == "lse":
                    s = sources.fetch_spark_lse(it["sym"])
                else:
                    s = []
            except Exception:
                s = []
            if s:
                with LOCK:
                    CACHE["sparks"][it["sym"]] = s
            return bool(s)

        items = list(CACHE["items"])
        missing = []
        for it in items:
            if not one(it):
                missing.append(it)
            time.sleep(0.8)  # 串行 + 间隔，避免被新浪限速（连发第 13 个曾返回空）
        if missing:  # 补一轮：给瞬时限流留时间，别让某只票整整 10 分钟没有线
            time.sleep(45)
            for it in missing:
                one(it)
                time.sleep(1.5)
        with LOCK:
            CACHE["spark_status"] = {
                "at": _now_iso(),
                "total": len(items),
                "ok": sum(1 for it in items if CACHE["sparks"].get(it["sym"])),
                "missing": [it["sym"] for it in items if not CACHE["sparks"].get(it["sym"])],
            }
        time.sleep(SPARK_TTL)


def _build_items():
    items = []
    for g, lst in cfg.GROUPS:
        for s in lst:
            market, ccy = cfg.MARKETS[s]
            items.append({"sym": s, "group": g, "market": market, "ccy": ccy,
                          "name": cfg.NAMES.get(s, s), "price": None, "prev_close": None,
                          "chg": None, "chg_pct": None, "ts": "", "stale": True})
    return items


def payload():
    with LOCK:
        items = []
        for it in CACHE["items"]:
            row = {k: v for k, v in it.items() if not k.startswith("_")}
            row["spark"] = CACHE["sparks"].get(it["sym"], [])
            items.append(row)
        return {"updated_at": _now_iso(CACHE["updated_at"]) if CACHE["updated_at"] else None,
                "items": items}


def _fmt_price(p, ccy):
    if p is None:
        return "—"
    if ccy in ("GBX",):
        return "%.1fp" % p
    return ("%.3f" % p) if p < 100 else ("%.2f" % p)


class Handler(BaseHTTPRequestHandler):
    server_version = "watchlist/1.0"

    def log_message(self, *a):  # 不把 ?k= 写进 access log
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/health":
            return self._send(200, {"ok": True, "updated_at": _now_iso(CACHE["updated_at"] or None),
                                    "sources": CACHE["sources"],
                                    "sparks": CACHE.get("spark_status", {})})
        if u.path == "/api/quotes":
            return self._send(200, payload())
        if u.path in ("/", "/index.html"):
            return self._serve_static("index.html")
        return self._serve_static(u.path.lstrip("/"))

    def _serve_static(self, name):
        path = os.path.realpath(os.path.join(STATIC_DIR, name))
        if not path.startswith(os.path.realpath(STATIC_DIR)) or not os.path.isfile(path):
            return self._send(404, {"error": "not found"})
        ctype = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                 ".js": "application/javascript; charset=utf-8",
                 ".webmanifest": "application/manifest+json", ".png": "image/png",
                 ".svg": "image/svg+xml"}.get(os.path.splitext(path)[1], "application/octet-stream")
        with open(path, "rb") as f:
            self._send(200, f.read(), ctype)


def main():
    with LOCK:
        CACHE["items"] = _build_items()
    refresh_once()
    threading.Thread(target=refresh_sparks, daemon=True).start()

    def loop():
        while True:
            t0 = time.time()
            try:
                refresh_once()
            except Exception:
                pass
            time.sleep(max(1, REFRESH_S - (time.time() - t0)))

    threading.Thread(target=loop, daemon=True).start()
    port = int(os.environ.get("WATCH_PORT", "8130"))
    # 生产用 127.0.0.1（1Panel 反代同机）；CI 冒烟容器需要 0.0.0.0 才能被 -p 映射到。
    bind = os.environ.get("WATCH_BIND", "127.0.0.1")
    srv = ThreadingHTTPServer((bind, port), Handler)
    print("watchlist listening on %s:%d" % (bind, port), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
