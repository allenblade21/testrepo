# AGENTS.md — 项目 Agent 操作手册（跨工具通用规范）

> 本文件是所有 AI Agent（Claude Code / 其他工具）与人类协作者的**共享契约与长期记忆入口**。
> Claude Code 通过根 `CLAUDE.md` 导入本文件；其他工具直接读取本文件。**开工前先读这里。**

## 1. 项目一句话

饮品比价系统：对**阿里闪购 / 京东 / 美团**三平台上的饮料饮品做「同商户跨平台到手价」比价。当前 **v0.5.2**，Mock 数据阶段，全链路可跑可测。

## 2. 仓库布局（先认清这个）

```
testrepo/
├── AGENTS.md / CLAUDE.md            ← 本手册（根级）
├── docs/                            ← ⚠️ 第一代 2 平台方案存档，已被下方主项目取代，勿在此开发
└── beverage-price-comparison/       ← ★ 当前主项目，所有开发都在这里
    ├── CLAUDE.md                    ← 项目级详细手册（模块地图/命令/坑）
    ├── CHANGELOG.md                 ← 唯一版本真相源（v0.1→现在）
    └── docs/                        ← 需求/设计/测试/上线/决策/复盘/状态看板
```

## 3. 铁律（不可违反，违反即回归）

1. **金额一律用「分」（整数）存储**，展示层才换算为「元」。
2. **同商户比价约束不可破**：可比单元内所有条目必须同一商户，三层保障（匹配键 / 构建断言 / `/compare` 409）一个都不能删。
3. **每次改动后必须跑 `python -m pytest -q`**，全绿才提交；改前端要另跑 E2E（见项目 CLAUDE.md）。
4. **提交前双端一致**：改了比价/搜索/定位逻辑，仓库版与 Artifact Demo 必须同步且结果一致。
5. **诚实标注 Mock**：当前价格是演示数据，界面「非真实价格」标注在真实数据接入前不得移除。
6. **测试哨兵不许绕过**：`test_catalog_coverage_sentinel` 等钉死数据构成的断言若报警，说明数据/匹配被动了，先查原因不要改哨兵迁就。

## 4. 常用命令

```bash
cd beverage-price-comparison
pip install -r requirements.txt
python -m pytest -q                                   # 全量单元/接口测试
python -m uvicorn app.main:app --port 8077            # 起服务（/=客户界面 /test=测试台）
node tests/e2e/load_more.spec.mjs <chrome路径>         # E2E：分页
node tests/e2e/geo_mobile.spec.mjs <chrome路径>        # E2E：移动端定位
docker compose up --build                             # 容器部署
```

## 5. 文档索引（去哪找什么）

| 想了解 | 看 |
| --- | --- |
| 项目怎么跑/模块地图/坑 | `beverage-price-comparison/CLAUDE.md` |
| 版本演进历史 | `beverage-price-comparison/CHANGELOG.md` |
| 系统怎么设计的 | `docs/设计文档.md` |
| 为什么这么决策 | `docs/决策记录.md`（ADR）|
| 踩过什么坑/经验 | `docs/复盘.md` |
| 当前进度/待办/谁在做什么 | `docs/状态看板.md` ← **多 Agent 协作先看这里** |
| 真实上线要什么 | `docs/真实上线需求文档.md` · `docs/上线计划.md` |
| 测试全景 | `docs/测试报告.md` |

## 6. 多 Agent 协作约定

- **`docs/状态看板.md` 是共享工作记忆**：开工前读「进行中」避免撞车；认领任务时在该区登记；完成后更新。
- **`docs/决策记录.md` 只追加不改旧条目**（append-only，天然无冲突）。
- **`CLAUDE.md`/`AGENTS.md` 是只读契约**：规则稳定，非必要不改；要改先在状态看板同步。
- 避免多 Agent 同时改同一份大文档；易变的「状态」与稳定的「设计」已拆开，按此分工。
- 每完成一个有意义的变更：跑测试 → 更新 CHANGELOG → 必要时补决策记录/复盘 → 更新状态看板 → 提交。
