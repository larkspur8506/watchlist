# watchlist —— 自选聚合页

单页展示全部持仓标的的实时涨跌幅（美股 ETF / 伦敦 ETF / BTC），设计参考富途「自选」。
零依赖：Python 3.12 stdlib 服务 + 一个静态页，容器约 50MB。

## 本地跑

```bash
WATCH_PORT=8131 python3 -m app.main
# 打开 http://127.0.0.1:8131/
python3 -m unittest discover -s tests -v
```

## 接口

| 路径 | 说明 |
|---|---|
| `GET /health` | 免 token，返回各源最近成功时间（供 1Panel / 巡检探活） |
| `GET /api/quotes` | 全量 JSON：`{updated_at, items:[{sym,group,ccy,price,chg,chg_pct,spark[],stale}]}` |
| `GET /` | 单页 |

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
  --env-file /opt/watchlist/.env --memory 192m \
  -v /var/lib/docker/volumes/wealthfolio/_data/wealthfolio.db:/data/wf.db:ro \
  ghcr.io/larkspur8506/watchlist:latest
```

`.env`：`WATCH_PORT=8130`、`WATCH_REFRESH_S=5`、`WF_DB=/data/wf.db`
页面无隐私数据（只展示涨跌幅），**不设访问口令**。

伦敦两只（IITU/VUAG）的迷你走势来自 Wealthfolio 的 `quotes` 表（同币种日收盘），
所以挂了这个只读卷；DB 不在时只是没有迷你线，不影响报价。
