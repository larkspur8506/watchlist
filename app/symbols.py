# -*- coding: utf-8 -*-
"""自选聚合页的标的清单（唯一需要改的配置文件）。

新增/清仓只动这里：group 决定页面分组顺序，ccy 决定价格单位的显示。
LSE 两只必须按各自交易单位写：IITU 以便士(GBX)报价，VUAG 以英镑(GBP)报价。
"""

GROUPS = [
    ("收入", ["SCHD", "DIVO", "GPIQ"]),
    ("增值", ["VOOG", "SPMO", "AVLV", "AVDV", "SCHG", "SCHV", "IDMO", "AVUV", "FRDM", "AVGE"]),
    ("伦敦", ["IITU", "VUAG"]),
    ("加密", ["BTC"]),
]

# 每个标的的市场 + 报价币种
MARKETS = {
    # 美股 ETF（Yahoo 代码即腾讯 us 前缀后的代码）
    "SCHD": ("us", "USD"), "DIVO": ("us", "USD"), "GPIQ": ("us", "USD"),
    "VOOG": ("us", "USD"), "SPMO": ("us", "USD"), "AVLV": ("us", "USD"),
    "AVDV": ("us", "USD"), "SCHG": ("us", "USD"), "SCHV": ("us", "USD"),
    "IDMO": ("us", "USD"), "AVUV": ("us", "USD"), "FRDM": ("us", "USD"),
    "AVGE": ("us", "USD"),
    # 伦敦（便士 / 英镑）
    "IITU": ("lse", "GBX"), "VUAG": ("lse", "GBP"),
    # 加密
    "BTC": ("crypto", "USD"),
}

# 页面上的中文短名（源里给的名字太长，移动端一行放不下）；缺省用源返回的名字
NAMES = {
    "SCHD": "Schwab 美国红利", "DIVO": "Amplify 收益", "GPIQ": "高盛纳指收益",
    "VOOG": "先锋 S&P500 成长", "SPMO": "景顺动量", "AVLV": "Avantis 美大盘价值",
    "AVDV": "Avantis 国际小盘价值", "SCHG": "Schwab 美国成长", "SCHV": "Schwab 美国价值",
    "IDMO": "Invesco 国际动量", "AVUV": "Avantis 美小盘价值", "FRDM": "自由新兴市场",
    "AVGE": "Avantis 全球全市场", "IITU": "iShares 标普科技", "VUAG": "先锋 S&P500 累积",
    "BTC": "比特币",
}


def all_symbols():
    return [s for _, lst in GROUPS for s in lst]


def group_of(sym):
    for g, lst in GROUPS:
        if sym in lst:
            return g
    return "其它"
