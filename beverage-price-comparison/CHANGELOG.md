# 更新日志（CHANGELOG）

本文件是**版本演进的唯一真相源**。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/)。
决策理由见 [docs/决策记录.md](docs/决策记录.md)，坑与复盘见 [docs/复盘.md](docs/复盘.md)。

> 测试计数随版本变化（部分版本因参数化用例随数据构成收敛而下降，属正常——见 v0.4.2）。

## [v0.8.1] 美团联盟真实 CPS API 接入（只差填密钥）
- **真实联盟客户端** `app/tuangou/union_client.py`：官方网关协议完整实现——`media.meituan.com/cps_open/common/api/v1/*`、HMAC-SHA256 签名（Content-MD5 + stringToSign + S-Ca-* 请求头）、`query_coupon`（到店到餐，经纬度×1e6）、`get_referral_link`（跟单计佣 deeplink）。
- **真实适配器** `union_adapter.py`：联盟商品券→GroupDeal 诚实映射——元→分、官方 `originalPrlice` 拼写兼容、标题解析人数档（解析不到=(1,99) 未知档）、不可售丢弃、**无菜品明细→降级标注**（ADR-011 兑现）、门店按品牌×商圈聚合（真实门店主数据映射待商家授权，P2-2）。
- **环境变量切源**：`TUANGOU_SOURCE=union` + `MEITUAN_UNION_APPKEY/SECRET[/BASE/SID]` 即切真实数据，**失败自动回退 Mock 保活**；新增探针 `GET /api/tuangou/health`（当前源/快照/数据量）。
- **契约仿真网关 + 端到端自动化测试**：`tests/tuangou/fake_union_gateway.py` 按同一算法**严格校验签名**；9 项集成测试（签名向量/往返/密钥错拒绝/映射/切源/坏密钥回退/网关不可达回退/默认 mock/真实冒烟 skip）。测试 152→**161 全绿 + 1 skip**。
- **真实密钥冒烟脚本** `tools/union_smoke.py`：拿到授权后一条命令验真，通过即切。

## [v0.8.0] 团购团餐比价新垂直 · G-R1 Mock 骨架
- **新垂直落地（G-R1）**：餐厅到店团购套餐比价，与饮品即时零售**同 App 双 Tab、下层隔离**（ADR-010）。新增 `app/tuangou/` 子模块，复用主系统适配器/Store 快照/geo/导出范式。
- **数据模型**（金额分存储）：`Restaurant / MenuItem / UsageRule / GroupDeal / ComparableDeal`；比价边界字段 `restaurant_id`（等价饮品 merchant）。
- **取数适配器**：`MockMeituanTuangouAdapter` 字段对齐美团联盟/CPS 可得范围；菜品明细列为**可能缺失字段**，缺失即 `has_menu_detail=false` + 界面标注降级（ADR-011）。
- **同门店约束三层保障**（复用 ADR-001）：匹配键首段=门店 + 构建断言门店唯一 + `/api/tuangou/compare` 跨门店 409。
- **团购到手价引擎**：`团购价 − 补贴(封顶不为负) + 包间费/服务费`，**人均到手价 = 到手价 ÷ 人数**（未选取区间中值）；复用饮品封顶不变式 `min()`。
- **API `/api/tuangou/*`**（延续 ADR-009/013 分路径）：`restaurants`（网格/菜系/人数召回）、`search`（关键词+人数+分页）、`compare`（到手价+人均+明细+使用规则+deeplink）。
- `tests/tuangou/` 35 项（模型/到手价/同门店三层/降级/API/种子哨兵）。测试 117→**152 全绿**。页面 `/tuangou` 与跨平台匹配（G-R2/R3）为后续里程碑。
- 设计见 `docs/团购比价设计文档.md`，决策 ADR-010~013，数据源接入 `docs/CPS接入条件与步骤.md`。

## [v0.7.0] 比价结果导出 PDF（带时间戳）
- **`POST /export`**：接收会话累积的比价记录，服务端用 reportlab（内置中文字体 STSong-Light）渲染真实 PDF，附件下载；**文件名与页眉均带时间戳**（东八区），最便宜行高亮、逐项明细表。
- **前端**：`app.html` 与 `discover.html` 新增「导出比价结果 PDF」按钮 + 会话比价记录累积（同商品同参数去重）+ 已比价计数 + 清空；无记录时按钮隐藏。
- **重构**：`/compare` 比价编排抽出 `_compute_comparison` 辅助，`/compare` 与 `/export` 共用（避免逻辑重复）。
- 依赖新增 `reportlab==5.0.0`。
- `tests/test_export.py` 8 项（PDF 头合法/多项/时间戳文件名/空→400/未知单元→404/超限→400/参数一致）+ `tests/e2e/export_pdf.spec.mjs`（并入 CI）。测试 117 项 pytest 全绿。
- 修复 CSS 特性：`.exportbar` 类选择器盖过 `[hidden]` UA 样式导致无法隐藏 → 补 `.exportbar[hidden]{display:none}`。

## [v0.6.0] 商户发现界面 + 双云发布流水线
- **商户发现 API `GET /api/discover`**：模糊商户搜索（商户上限 20、网格过滤 + 地点排名）+ 命中商户下商品扁平化**分页**（100/页），返回 merchant_total/product_total。
- **商户发现界面 `/discover`（web/discover.html）**：清晰三步流程（定位→模糊搜商户→商品分页），商户 chip 钻取、上/下一页、内联比价；GPS 授权/网格过滤/手机平板适配沿用 v0.5.x。
- **重构**：抽出 `_merchant_groups`/`_product_brief`/`_sorted_units` 共享辅助，`/merchants` 与 `/api/discover` 复用，消除聚合逻辑重复。
- **发布流水线**：`.github/workflows/deploy-aliyun.yml`（后端 ACR/SAE + 前端 OSS）与 `deploy-volcengine.yml`（后端 CR/VKE + 前端 TOS），前后端分离、双云适配；文档见 `docs/部署流水线.md`。
- `tests/test_discover.py` 12 项（模糊/商户上限/商品分页不重不漏/网格排名/可比价）+ E2E 实测（分页/钻取/比价/手机无溢出）。测试 97→109（+E2E discover）。

## [v0.5.2] 手机/平板 Chrome 适配 + 内嵌态识别 + 健壮性修复
- 新增平板断点（641–1024px 两列比价）；窄屏位置胶囊换行、面板全宽可滚、触控目标 ≥40px。
- 识别嵌入(iframe/预览)场景：浏览器禁止内嵌页定位且不弹窗，改为准确指引。
- **修复 2 个 E2E 揪出的真实 bug**：① `localStorage` 内嵌/隐私模式抛异常致整页崩溃 → `safeStore` 封装；② 检查顺序（内嵌态优先于非安全上下文）。
- 新增 `tests/e2e/geo_mobile.spec.mjs`（21 断言）并入 CI。pytest 97 项零回归。

## [v0.5.1] GPS 显式权限申请
- 点击定位先用 Permissions API 预探测：已拒绝态给「地址栏🔒→允许位置→刷新」指引；未询问/已授权态调起原生弹窗。
- 补充非安全上下文/超时/位置不可用/网络异常分支与按钮态恢复。pytest 97 项零回归。

## [v0.5.0] 定位与商圈网格（真实上线 PRD §4 骨架）
- `geo_data.py` 4 商圈网格 + 16 商户坐标/评分/月售（Mock）。
- `GET /grids`、`GET /grid/resolve`（坐标→网格，坐标不落库，超 3km 提示不在服务区）。
- `/search`、`/merchants` 新增 `grid` 参数（网格过滤零泄漏，默认不传=全库，向后兼容）；聚合带 grid 按排名分降序并透出因子。
- 客户界面位置胶囊（GPS 授权/拒绝/区外三级降级）。`tests/test_geo.py` 13 项。测试 84→97。

## [v0.4.2] 平台缺口补齐
- `tools/fill_platform_gaps.py` 为生成目录 67 个两平台单元确定性补上缺失平台（条目 278→345，单元 ID 零扰动）。平台分布 {2:70,3:46}→**{2:3,3:113}**。
- **有意保留 3 个两平台单元**：永辉·元气森林(缺美团,S4缺货降级)、罗森·可乐(缺京东,S2商户隔离)、喜茶·多肉葡萄(缺京东,S10起送)。
- 参数化用例随构成收敛（测试 173→84，忠实反映数据分布），哨兵更新为 116/3/1/1。

## [v0.4.1] 生产化基础（上线计划阶段一）
- `DataStore` 可重建快照：`POST /admin/refresh`（令牌保护）+ `REFRESH_INTERVAL_S` 定时刷新（失败保留旧快照）。
- `/compare` 返回 `price_as_of` 新鲜度；请求日志 + `GET /metrics`（P50/P95/P99）；滑动窗口限流（health 豁免）+ CORS + 环境变量配置。
- Dockerfile / docker-compose / GitHub Actions CI（pytest+E2E）。测试 165→173。

## [v0.4.0] 商户直达（聚合查询）
- 新增聚合 API `GET /merchants?q=`（按商户名聚合全部商品名列表）。
- 客户界面第二搜索框，实时（防抖+过期响应丢弃）聚合、分组渲染、点击直达比价。测试 158→165。

## [v0.3.4] 平台覆盖专项测试
- 为 70 个两平台 + 23 个缺美团 + 起送拦截单元逐一参数化 + 目录哨兵 + 116 单元全库扫描（`tests/test_coverage.py`）。测试 62→158。

## [v0.3.3] BUG-003 修复：加载更多防抖竞态
- 「加载更多」误用输入框实时值致「已显示>共计」错乱 → 追加请求钉死列表所属查询词。
- 新增 E2E `tests/e2e/load_more.spec.mjs`（12 断言）+ 后端分页契约 2 项。测试 60→62。

## [v0.3.2] BUG-002 修复：起送价商户级
- 起送价由平台级迁为**商户×平台级**门店属性（`STORE_MIN_ORDER`，未配置=0，对所有品类生效）。
- 瑞幸美团不足 ¥20 恢复可下单并成最优（S5 改写）；喜茶美团 ¥26 承担起送拦截（S10）。`tests/test_min_order.py` 7 项。测试 53→60。

## [v0.3.1] 正式搜索 API
- 全商户产品库检索、相关度排序、limit/offset 分页；客户界面输入即搜+加载更多+选择比价。测试 50→53。

## [v0.3] 每日首单券 + 双入口界面
- 每日首单券进入比价口径与界面（默认全勾、门槛按扣减后应付判断，API 默认不启用保基线）。
- 界面拆分：`/` 客户界面 + `/test` 测试报表控制台。测试 40→50。

## [v0.2.2] 手机自适应与主流浏览器兼容

## [v0.2.1] 边界测试 + BUG-001 修复
- 边界测试 16 项；修复满减/券未封顶导致到手价可为负。

## [v0.2] 商户约束重构
- 比价严格限定同商户，商户贯穿模型/匹配/接口/前端；端到端测试报告 + 组件架构图。测试 14→24。

## [v0.1] MVP
- 三平台饮品比价：条码/品名规格匹配、到手价引擎、并排比价前端。测试 14 项。
