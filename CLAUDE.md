# CLAUDE.md

本仓库的 Agent 操作手册与共享契约以 **AGENTS.md** 为准（下方导入），项目级细节见 `beverage-price-comparison/CLAUDE.md`。

@AGENTS.md

## Claude Code 专属提示

- 主项目在 `beverage-price-comparison/`，进入后再看该目录的 `CLAUDE.md`（模块地图、命令、常见坑）。
- 停后台服务用括号技巧避免 pkill 自匹配：`pkill -f "[u]vicorn app.main"`；**kill 与 start 分两条命令执行**，勿写在同一条复合命令里。
- 版本历史唯一真相源是 `beverage-price-comparison/CHANGELOG.md`——改动请更新它，不要再往设计文档里堆版本表。
