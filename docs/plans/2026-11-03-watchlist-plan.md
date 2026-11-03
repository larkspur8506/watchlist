# 自选聚合页（watchlist）开发计划

**目标**：单页、打开即看——把当前全部投资标的（13 只美股 ETF + 2 只伦敦 ETF + BTC + 现金）的**实时涨跌幅**一屏列完，视觉参考富途「自选」页。
**形态**：只读聚合页，不做交易、不接券商下单；数据全部来自公开行情源，服务端聚合，前端 5 秒刷新。
**部署**：oracle1 新容器 `watchlist`（127.0.0.1:8130）→ 1Panel 反代 → 独立子域 + HTTPS + 页面 token。复用 trade-hub 的成熟模式（ghcr 镜像 / GH Actions 发布 / `?k=` 页门 / PWA 图标 / CF 橙云 + 自签源站证书）。

## 1. 标的清单（源：Wealthfolio 2026-10-25 快照）

| 分组 | 标的 |
|---|---|
| 收入 | SCHD、DIVO、GPIQ |
| 增值 | VOOG、SPMO、AVLV、AVDV、SCHG、SCHV、IDMO、AVUV、FRDM、AVGE |
| 伦敦（GBp） | IITU、VUAG（便士价，必须标 p 不能标 £） |
| 加密 | BTC（Binance BTCUSDT） |
| 现金 | Kraken 稳定币（不涨跌，显示计息 4.1%，静态） |
| 可选观察 | 创业板指 399006、上证 000001（富途自选页底部就有一条指数） |

合计 15 个会动的标的。新增/清仓只改一份 `symbols.yaml`，不碰代码。

## 2. 数据源（本次已实测，全部免 key、从 Hermes 容器与 oracle1 都能直连）

| 用途 | 源 | 实测结果 |
|---|---|---|
| 美股/港股/A股报价 | `qt.gtimg.cn/q=usSCHD` | ✅ GBK，字段以 `~` 分隔；`[3]`现价 `[4]`昨收 `[31]`涨跌额 `[32]`涨跌幅 `[30]`时间。**带 `access-control-allow-origin: *`** |
| 美股报价（备源，字段更全） | `hq.sinajs.cn/list=gb_schd` | ✅ 需 `Referer: finance.sina.com.cn`；含盘前/盘后与更细时间戳 |
| 美股日线（迷你图） | `stock.finance.sina.com.cn/usstock/api/jsonp.php/.../US_MinKService.getDailyK?symbol=SCHD` | ✅ 全历史 JSONP；**腾讯的美股 K 线只有当天 1 根，不能用** |
| A股/指数日线 | `web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sz399006,day,...` | ✅ 实测 40 根 |
| 伦敦 ETF | `hq.sinajs.cn/list=lse_iitu,lse_vuag` | ✅ 有数据（`iitu,3721,3765,...`），但**字段含义无文档，需开盘后逐字段校准**（用 Wealthfolio 里的 £ 估值行反推） |
| BTC | `api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT` | ✅ 77,051 / -1.87% |

**关键待验证项（M0，开盘后才可做）**：腾讯美股 K 线响应里 `qt[0]` 返回 `"delay"`，说明美股报价可能是**延迟 15 分钟**。新浪美股带盘前盘后时间戳，看起来更接近实时。M0 必须在美股开盘时（UTC 13:30 后）用同一分钟的三个源（腾讯 / 新浪 / 富途截图）比对，**确认延迟档位后再定主源**。若免费源全是 15 分钟，要提前告知：这叫"准实时"，不是真实时；真实时需要付费源（Polygon/Alpaca 或 IBKR 行情权限）。

## 3. 架构

```
[1Panel nginx] --(wl.222677.xyz, ?k=token)--> [watchlist 容器 127.0.0.1:8130]
                                                ├─ 后台线程每 5s 抓三大源 → 内存缓存
                                                ├─ GET /api/quotes   全量 JSON（带 token 校验）
                                                └─ GET /           单页 HTML/CSS/JS（PWA 图标）
```

- **为什么不做纯前端直连**：伦敦两只必须服务端带 `Referer`，美股迷你图走 JSONP，且后端能统一缓存/降频/换源，避免每个设备各自打第三方接口被限速。
- 休市自动降频：报价时间戳 5 分钟不变 → 轮询降到 60s；无变化不重绘（避免手机耗电）。
- 全量 JSON 估算 <8KB，5s 一刷对 1G 内存机器无压力。

## 4. 页面规格（对齐富途自选）

- 暗色底（`#0b0b0c`）+ 分组吸顶小标题；每行 56px：`代码` + `中文名`（灰小字）/ `现价`（等宽数字，右对齐）/ `涨跌幅`（红涨绿跌，可全局切换成绿涨红跌）/ 右侧 48×20 迷你走势线。
- 顶部：(左) 标题「自选」+ 数据源时间戳；(右) 手动刷新 + 主题切换。**不显示账户金额**（v1）。
- 底部：总览条——上涨 N / 下跌 N / 平盘 N + 组合当日加权涨跌幅（按持仓市值权重，需要金额时走 token 后显示）。
- 排序：默认按自定义顺序（分组内按仓位大小），支持点列头切「涨跌幅」「名称」。
- 空态/异常：某标的抓取失败 → 该行保留价格但整行降透明度 + 右上角琥珀点「数据 15s 未更新」；全部失败 → 页面顶部横幅「行情源不可用」，不显示 0.00% 假跌。
- 移动优先（390px 不横向滚动）——这是 trade-hub 踩过的「破窗」坑，直接沿用那套三层修法。

## 5. 任务拆分（每项都可独立验收）

**T1 数据源适配层**（`app/sources.py`）
- `fetch_tencent(symbols) -> dict`、`fetch_sina_us`、`fetch_sina_lse`、`fetch_daily_k(symbol, n=20)`、`fetch_btc()`
- 三市场字段映射表（美股 `~` 第 3/4/31/32 位、A股指数布局不同、LSE 待校准）
- 单测：GBK 解码、字段错位、停牌（成交量为 0）、缺失标的（返回空串 `var hq_str_gb_iitu=""`）、非交易时段涨跌为 0 不误报
- 验收：`python -m pytest tests/test_sources.py` 全绿 + 手工打印 15 个标的的现价与涨跌幅，和富途截图逐一对上

**T2 聚合服务**（`app/main.py`）
- `GET /api/quotes?k=<token>` → `{updated_at, session, items:[{sym,name,group,ccy,price,chg,chg_pct,spark:[...],stale}]}`
- 后台线程 5s 刷新 + 失败不清空旧值（只打 stale 标记）
- `GET /health` 返回 ok + 各源最近一次成功时间
- 验收：`curl /api/quotes` 两次间隔 6s，价格/时间戳会动；断网模拟 → `stale: true` 而非空数组

**T3 页面**（`app/static/`）
- `index.html` + `app.css` + `app.js`：分组渲染、5s 轮询、涨跌色、sparkline（canvas 或内联 SVG path）
- 验收：390px 下 `document.documentElement.scrollWidth == innerWidth`；颜色与富途截图同向（红涨）

**T4 部署**
- GH Actions 构建 `ghcr.io/larkspur8506/watchlist`（tag = sha + latest）
- oracle1：`docker run -d --name watchlist --network host --env-file /opt/watchlist/.env ... 127.0.0.1:8130`
- 1Panel 建站 `wl.222677.xyz` → 反代 127.0.0.1:8130；CF 橙云 A 记录；源站自签 10 年证书（与 hub 同法）
- 验收：公网 `https://wl.222677.xyz/health` 200；不带 `?k=` 返回 401

**T5 打磨**（可选，先不做）
- 排序切换、分组折叠记忆、PWA 图标（复用 trade-hub 的 Lucide 管线）、休市降频、多源自动回退

## 6. 风险

| 风险 | 处置 |
|---|---|
| 腾讯/新浪是非官方接口，随时改字段或封 IP | 双源（腾讯主、新浪备）自动回退；解析失败只影响单标的；缓存兜底 |
| 免费源美股延迟 15 分钟 | M0 开盘实测；若确认延迟，页面明确标注「延迟 15 分钟」，不写"实时" |
| LSE 字段无文档 | 用 Wealthfolio £ 估值反推校准，写进单测 fixture |
| 公网页面泄露持仓结构 | v1 只显示涨跌幅不显示金额；金额需 token；页面整体 `?k=` 门禁 |
| oracle1 内存只有 952Mi | 容器内存限制 128Mi，无前端构建产物，纯静态 |

## 7. 里程碑

- M0 开盘实测延迟档位（30 分钟）
- M1 T1+T2 数据层跑通，命令行能看到 15 个标的实时数据（半天）
- M2 T3 页面成型，本机手机尺寸预览（半天）
- M3 T4 上线到 wl 子域（半天）
- M4 打磨与 PWA（半天，可延后）

## 8. 待你拍板

1. **域名**：`wl.222677.xyz`（推荐，符合一服务一域名）还是挂到现有的 `hub.sqqq.de5.net` 下面 `/watch`？
2. **范围**：v1 只要涨跌幅，还是同时要「总市值 + 当日盈亏」总览条（后者需要读 Wealthfolio 持仓金额，页面必须带 token）？
3. **颜色**：默认红涨绿跌（富途中国版），要不要给个开关切绿涨红跌？
