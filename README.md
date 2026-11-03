# watchlist —— 自选聚合页

单页展示全部持仓标的的实时涨跌幅（美股 ETF / 伦敦 ETF / BTC），设计参考富途「自选」。
零依赖：Python 3.12 stdlib 服务 + 一个静态页，容器约 50MB。

## 本地跑

```bash
WATCH_TOKEN=dev123 WATCH_PORT=8131 python3 -m app.main
# 打开 http://127.0.0.1:8131/?k=dev123
python3 -m unittest discover -s tests -v
```

## 接口

| 路径 | 说明 |
|---|---|
| `GET /health` | 免 token，返回各源最近成功时间（供 1Panel / 巡检探活） |
| `GET /api/quotes?k=<token>` | 全量 JSON：`{updated_at, items:[{sym,group,ccy,price,chg,chg_pct,spark[],stale}]}` |
| `GET /?k=<token>` | 单页 |

## 数据源（都是非官方免费接口，实测记录见 `app/sources.py` 注释）

- 美股报价：新浪 `hq.sinajs.cn/list=gb_*`（主）/ 腾讯 `qt.gtimg.cn`（备）
- 伦敦报价：新浪 `lse_*`，IITU 是便士、VUAG 是英镑
- BTC：Binance `/api/v3/ticker/24hr`
- 迷你走势：新浪美股 `US_MinKService.getDailyK`、Binance klines（腾讯美股 K 线只有当天 1 根，不可用）

## 部署

镜像 `ghcr.io/larkspur8506/watchlist`（tag = `sha-<短sha>` / `latest`），由 `.github/workflows/publish.yml` 构建。
oracle1 上以 host 网络跑在 `127.0.0.1:8130`，1Panel 反代 `wl.sqqq.de5.net`。

```bash
docker run -d --name watchlist --network host --restart unless-stopped \
  --env-file /opt/watchlist/.env ghcr.io/larkspur8506/watchlist:latest
```

`.env`：`WATCH_TOKEN=<口令>`、`WATCH_PORT=8130`、`WATCH_REFRESH_S=5`
