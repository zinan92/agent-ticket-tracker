# 03 - Single-entry implicit tracker attach

**Status:** claimed

**GitHub issue:** #5

## Outcome

让现有 workflow 保持一个用户入口：用户继续使用原有 slash command，workflow 内部可以隐形 attach 一个只读 Agent Ticket Tracker。

## Acceptance criteria

- [ ] `att attach --project <path>` 幂等登记项目并返回可复用的 loopback dashboard URL；登记只写 tracker 自己的用户目录。
- [ ] attach 不要求 feature slug；`feature=auto` 在没有 source 时等待，出现唯一 `.scratch/<feature>/spec.md` 与 `issues/` 后自动跟随，多个候选时 fail closed。
- [ ] attach 复用健康 observer，失效时只重启 tracker observer，不启动任何 executor。
- [ ] `/api/state`、dashboard 和 `wake` 保持 read-only，不改变 manifest、ticket、代码、branch、PR 或 Agent 状态。
- [ ] 提供内部 hook skill/协议；用户不需要输入第二个 slash command。
- [ ] 测试覆盖 attach、auto discovery、ambiguity、服务复用和目标项目无写入。

## In scope

- tracker-owned user registry、幂等 attach、auto feature discovery、loopback observer lifecycle。
- 可安装的内部 hook skill 和全局单入口接入说明。

## Out of scope

- 任何 ticket/代码/branch/PR/Agent 状态修改。
- `/implement` 的重试、暂停、恢复、终止或调度。
- GitHub/Linear 写入、云端服务、跨机器协作。
- 盲目扫描整个磁盘或自动纳入未声明的目录。

## 禁区

Tracker 只能登记自己的 observer 元数据并读取项目；不能把 attach 变成 workflow router，不能在缺少边界时猜测或启动执行。
