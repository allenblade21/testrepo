# 比价系统（Price Comparison Platform）

饮品/即时零售比价平台。**当前主项目为三平台（阿里闪购 / 京东 / 美团）饮品比价系统**，位于 [`beverage-price-comparison/`](beverage-price-comparison/)。

## 快速导航

| 我想… | 去 |
| --- | --- |
| 了解 Agent 协作规则/命令/铁律 | [AGENTS.md](AGENTS.md) · [CLAUDE.md](CLAUDE.md) |
| 进入当前主项目 | [beverage-price-comparison/](beverage-price-comparison/)（先读其 `CLAUDE.md`）|
| 看版本历史 | [beverage-price-comparison/CHANGELOG.md](beverage-price-comparison/CHANGELOG.md) |
| 看当前进度/待办 | [beverage-price-comparison/docs/状态看板.md](beverage-price-comparison/docs/状态看板.md) |
| 早期 2 平台方案（已存档）| [docs/](docs/)（⚠️ 历史存档，勿开发）|

## 仓库结构

```
testrepo/
├── AGENTS.md / CLAUDE.md            Agent 操作手册（根级共享契约）
├── docs/                           ⚠️ 第一代 2 平台方案存档（已被主项目取代）
└── beverage-price-comparison/      ★ 当前主项目（v0.5.2）
    ├── CLAUDE.md                   项目级手册
    ├── CHANGELOG.md                版本历史（唯一真相源）
    ├── app/ web/ tests/ tools/     后端 / 前端 / 测试 / 离线工具
    └── docs/                       设计·需求·测试·上线·决策·复盘·状态看板
```
