# Agent Ticket Tracker Registry

## 现在在哪里

- 本地分类：`Agent｜Build`
- 本地路径：`/Users/wendy/Documents/Codex/Workspaces/agent-build/agent-ticket-tracker`
- Public GitHub：<https://github.com/zinan92/agent-ticket-tracker>
- 当前主线：`main` at `f5bb951`
- MVP Issue：<https://github.com/zinan92/agent-ticket-tracker/issues/1>
- MVP PR：<https://github.com/zinan92/agent-ticket-tracker/pull/2>
- Read-only observation issue：<https://github.com/zinan92/agent-ticket-tracker/issues/3>

## 现在能做什么

- 为项目创建 `.agent-ticket-tracker/<feature>/manifest.json`；
- 读取固定位置的 local Markdown spec 和 tickets；
- 在 localhost 展示 map-first delivery view；
- 计算 verified、blocker 和 frontier；
- 用 `wake` 输出下一步 continuation brief；
- 在 Codex App 的浏览器面板中打开本地 UI。
- 以 read-only observer/dashboard 方式读取项目过程信号，不拥有开发流程状态；
- 在每次读取时展示 spec/ticket 文件和 Git branch、working-tree、latest commit 的 observations；
- 在 dashboard 和 `wake` 中输出观察摘要，不触发任何 command；
- local Markdown 导入默认产生 `ticket` 节点；Wayfinder `decision` 节点需要 manual manifest，专用 adapter 尚未实现。

## 明确不能做什么

- 不读取实时 GitHub/Linear/PR 状态；
- 不启动、暂停、重试或合并 Agent 工作；
- 不修改被监控项目的源代码、分支、remote 或凭证；
- 不把 Agent 自报、缺失证据或 stale evidence 变成绿色状态；
- 不注入 Codex App 原生侧边栏。

## 下一步

1. 在一个真实项目上运行 5-ticket pilot，记录 verified-software 与 verified-experience 的差异。
2. 优先增加额外的只读数据源 adapters，例如 GitHub、Linear、PR 和 receipts。
3. 不把 executor adapter 纳入 tracker 产品契约；执行仍由 `/implement` 等 command 负责。
