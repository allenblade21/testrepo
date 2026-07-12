# 饮品比价系统 🥤

对 **阿里闪购 / 京东 / 美团** 三个平台上的**饮料饮品**进行到手价比价。搜一款饮品，三平台到手价并排展示，自动标出最便宜方与节省金额。

> 设计文档（含组件架构图）见 [docs/设计文档.md](docs/设计文档.md)；**整体架构图与商品抽取原理**见 [docs/商品抽取API原理.md](docs/商品抽取API原理.md)；端到端测试报告见 [docs/测试报告.md](docs/测试报告.md)。

## 功能

- **同商户比价约束** ⭐：比价的每一个产品都限定在**相同商户（门店）**下——同款商品由不同商户售卖时拆为独立可比单元，互不混比（匹配键/构建断言/接口校验三层保障）
- **跨平台匹配**：商户内瓶装标品按条码精确匹配；现制饮品按「品牌+品名+规格」归一化匹配（自动吸收 `/`、空格、全角空格等写法差异）
- **到手价引擎**：售价 − 第二件半价/满减/补贴/券 + 配送费，输出透明明细
- **三平台并排比价**：高亮最便宜方、展示节省金额、识别缺货/单边可比、现制饮品起送价校验
- **商户直达（聚合查询）**：第二个搜索框实时调用聚合 API `/merchants`，按商户名聚合展示该商户全部商品名列表，点击直达比价
- **可插拔适配器**：每平台一个适配器，当前为 Mock（读种子数据），未来接真实数据源只换适配器、上层不动

## 技术栈

Python + FastAPI · SQLite（内置种子数据）· 原生 HTML/JS 前端 · pytest

## 本地运行

```bash
cd beverage-price-comparison
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8077
```

## 容器运行 / 生产配置

```bash
docker compose up --build   # 端口 8077；环境变量见 .env.example
```

生产化能力（v0.4.1，配置全部环境变量驱动）：数据快照定时刷新（`REFRESH_INTERVAL_S`）+ 手动刷新（`POST /admin/refresh`，`ADMIN_TOKEN` 保护）、`/metrics` 延迟指标（P50/P95/P99）、请求限流（`RATE_LIMIT_PER_MIN`，`/health` 豁免）、CORS（`CORS_ORIGINS`）、`/compare` 返回 `price_as_of` 价格新鲜度。CI 见 `.github/workflows/ci.yml`（push/PR 自动跑 173 项测试 + E2E）。上线路线见 [docs/上线计划.md](docs/上线计划.md)。

两个界面入口：

- **`/`** — 正式客户使用界面（搜索、每日首单券勾选、三平台并排比价）
- **`/test`** — 测试 + 报表控制台（系统状态、S1–S9 自动化场景报表、交互测试台）

搜索「可乐 / 永辉 / 罗森 / 元气森林 / 喜茶 / 瑞幸」试试（商品名和商户名都能搜）。

## 运行测试

```bash
cd beverage-price-comparison
python -m pytest -q
```

## 接口

| 接口 | 说明 |
| --- | --- |
| `GET /search?q=可乐` | 关键词召回可比饮品 |
| `GET /compare?unit_id=xxx&qty=1&include_delivery=true` | 某饮品三平台到手价对比 |
| `GET /health` | 健康检查 |
| `GET /` | 前端页面 |

FastAPI 自带交互式接口文档：<http://127.0.0.1:8077/docs>

## 目录结构

```
beverage-price-comparison/
├── docs/
│   ├── 设计文档.md       设计文档（含组件架构图）
│   ├── 测试报告.md       7 场景端到端 + 24 项 pytest 汇总
│   └── img/              各场景 UI 截图
├── app/
│   ├── main.py           FastAPI 入口 + 比价编排 + 商户校验
│   ├── models.py         数据模型（Listing 含 merchant）
│   ├── db.py             SQLite + 种子数据
│   ├── matching.py       跨平台匹配引擎（商户+商品 单元键）
│   ├── pricing.py        到手价计算引擎
│   └── adapters/         平台适配器（阿里闪购/京东/美团，Mock 可插拔）
├── web/index.html        前端页面（商户标签）
├── tests/                pytest 24 项（商户约束 + 匹配 + 算价 + 接口）
├── seed_data.py          Mock 种子数据（商户×商品×优惠）
└── requirements.txt
```

## 数据说明

当前使用 **Mock 种子数据**（演示用，非真实价格），目的是让全流程在沙盒/本地即可运行验证。三大平台无公开免费比价接口，接入真实数据需官方授权或合规采集——届时只需替换 `app/adapters/` 下的适配器实现，匹配/算价/比价/展示逻辑无需改动。
