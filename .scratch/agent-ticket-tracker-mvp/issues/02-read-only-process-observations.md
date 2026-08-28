# 02 - Read-only process observations

**Status:** claimed

**GitHub issue:** #3

## Outcome

让 Agent Ticket Tracker 只读地提取真实项目已经产生的活动信号，并在 dashboard / wake 中展示最近发生了什么。Tracker 仍然只是观察层，不成为执行器或状态机。

## Acceptance criteria

- [ ] `load_state` 返回有限、结构化的 recent observations，且不修改项目文件、Git 状态或 tracker manifest。
- [ ] 观察 spec/ticket/artifact 的可读变化，以及 Git branch、working-tree summary 和最近提交；缺失或无法读取时显示 unavailable/unknown。
- [ ] observations 只用于展示，不覆盖 ticket status、acceptance、evidence、blocker 或 green/frontier 规则。
- [ ] dashboard 显示 observation 摘要和最后观察时间；`wake` 输出同样的只读摘要。
- [ ] malformed、missing、Git 读取失败或不安全路径时 fail closed，不触发任何执行，也不产生新的 actionable frontier。
- [ ] 测试覆盖 Git 项目、无 Git 项目、读取失败/不安全路径，并证明观察请求没有修改目标目录。

## In scope

- 只读 filesystem metadata、声明的 artifact reads 和 Git read-only inspection。
- normalized observation schema、dashboard observation panel、wake brief。
- README/REGISTRY 对 observer-only 边界的澄清。

## Out of scope

- 调度、启动、重试、暂停、恢复、终止任何 Agent 或 command。
- 创建或修改 issue、PR、branch、代码、manifest、receipt 或其他项目状态。
- Codex App 原生插件、后台 daemon、notification delivery、GitHub/Linear API 写入。

## 禁区

Tracker 不能调用 `/implement` 或任何 executor；不能把最近有文件变化解释成已完成；不能让 observation 自动改变任何状态。
