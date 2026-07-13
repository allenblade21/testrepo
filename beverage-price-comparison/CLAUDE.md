# CLAUDE.md — 饮品比价系统（项目级手册）

> 根手册见 `../AGENTS.md`（铁律/命令/协作约定）。本文件是**项目内部细节**：模块地图、数据流、常见坑、修改流程。

## 模块地图（改哪里找这里）

### 后端 `app/`
| 文件 | 职责 | 改动注意 |
| --- | --- | --- |
| `main.py` | FastAPI 入口、全部路由、比价编排、可观测/限流中间件 | 路由与编排都在这；请求处理走 `store.*`，勿用模块级旧全局量 |
| `models.py` | 数据模型 Listing / ComparableUnit / Promotion / DeliveryPolicy | `Listing.merchant` 是比价边界字段，勿去掉 |
| `db.py` | SQLite 建库灌数（listing/promotion/delivery 三表）| |
| `store.py` | 可重建数据快照 `DataStore.rebuild()` | 单元 ID 由内容哈希派生，重建不改已有 ID |
| `config.py` | 环境变量配置（刷新/限流/CORS/令牌）| 全有安全默认，开发零配置 |
| `matching.py` | 匹配引擎，单元键=`商户+条码|品名规格`，归一化、搜索 | 归一化器吸收 `/`、空格、全角空格 |
| `pricing.py` | 到手价引擎；优惠顺序 `_KIND_ORDER` | 每项减免封顶于应付（到手价恒非负）——勿删这个 min() |
| `geo.py` | 网格解析 + 排名分（0.35覆盖+0.25销量+0.20距离+0.20评分）| 排名分必须与公示因子加权一致（有测试锁）|
| `adapters/` | 平台适配层（可插拔），当前 Mock 读 SQLite | 接真实数据只换这层，上层零改动 |

### 数据源（Mock，固定种子可复现）
- `seed_data.py`：4 家核心商户手工数据，**承载 S1–S10 场景基线，永不重生成**（含起送价 `STORE_MIN_ORDER`、首单券 `FIRST_ORDER_COUPON`）。
- `catalog_data.py`：生成目录（勿手改），由 `tools/generate_catalog.py` + `tools/fill_platform_gaps.py` 产出。
- `geo_data.py`：4 商圈网格 + 16 商户坐标/评分/月售。

### 前端 `web/`（三入口）
- `app.html`（`/`）：正式客户比价界面（搜索/定位胶囊/首单券/比价）。
- `discover.html`（`/discover`）：商户发现界面（GPS+模糊搜商户+商品分页+内联比价），调 `/api/discover`。
- `test.html`（`/test`）：测试+报表控制台（S1–S10 自动报表）。
- **注意路由**：`/discover` 是页面，`/api/discover` 是数据 API（勿再让页面与 API 同路径，否则 FastAPI 路由冲突）。
- **Artifact Demo**（scratchpad 里的 `beverage-demo.html`）是同构 JS 副本，改前端逻辑要同步它并重新发布。

### 测试 `tests/`
pytest 97 项 + E2E（`e2e/load_more.spec.mjs` 分页、`e2e/geo_mobile.spec.mjs` 移动定位）。

## 数据流

**启动**：`seed_data`+`catalog_data` → `db.init_db` 灌库 → 三平台 Adapter 抽取 → `matching.build_units` 归并成 116 可比单元 → 常驻 `store`。
**查询**：`/search`（相关度+分页+网格过滤）、`/merchants`（商户聚合+地点排名）、`/compare`（商户校验→逐平台算价→最优评选）。详见 `docs/商品抽取API原理.md`。

## 常见坑（血泪教训，详见 docs/复盘.md）

1. **`pkill -f "uvicorn..."` 会杀掉自己的 shell**（命令行自匹配）→ 用 `pkill -f "[u]vicorn app.main"`，且 kill/start 分开执行。
2. **`localStorage` 在内嵌/隐私模式抛异常会整页崩溃** → 前端一律走 `safeStore` 封装。
3. **iframe 内定位被浏览器禁止且不弹窗**（Artifact 就是 iframe）→ 前端检测 `window.self!==window.top` 给指引；真实弹窗需独立 HTTPS 页面。
4. **改优惠/起送逻辑后 S1–S10 报表数字会漂** → 跑 `/test` 或 Demo 报表确认仍 10/10。
5. **改动数据构成**（如重生成目录）→ 更新 `test_catalog_coverage_sentinel` 哨兵数字（当前 116/3/1/1）。

## 修改流程（每次改动照做）

1. 改代码 → `python -m pytest -q` 全绿；
2. 改了前端 → 起服务跑对应 E2E；改了比价/搜索/定位 → 同步 Artifact Demo 并重新发布，确认双端结果一致；
3. 有版本意义 → 更新 `CHANGELOG.md`；重大决策 → 追加 `docs/决策记录.md`；踩坑/修 bug → 追加 `docs/复盘.md`；
4. 更新 `docs/状态看板.md`；
5. 提交（commit message 写清 what+why）→ push。
