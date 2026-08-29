# Agent Ticket Tracker Registry

## 现在在哪里

- 本地分类：`Agent｜Build`
- 本地路径：`/Users/wendy/Documents/Codex/Workspaces/agent-build/agent-ticket-tracker`
- Public GitHub：<https://github.com/zinan92/agent-ticket-tracker>
- 当前主线：`main` at `9aeb581`
- MVP Issue：<https://github.com/zinan92/agent-ticket-tracker/issues/1>
- MVP PR：<https://github.com/zinan92/agent-ticket-tracker/pull/2>
- Read-only observation issue：<https://github.com/zinan92/agent-ticket-tracker/issues/3>
- Read-only observation PR：<https://github.com/zinan92/agent-ticket-tracker/pull/4>
- Implicit attach issue：<https://github.com/zinan92/agent-ticket-tracker/issues/5>
- Implicit attach PR：<https://github.com/zinan92/agent-ticket-tracker/pull/6>
- Real source adapter issue：<https://github.com/zinan92/agent-ticket-tracker/issues/7>
- Real source adapter PR：<https://github.com/zinan92/agent-ticket-tracker/pull/8>
- Observer port restart PR：<https://github.com/zinan92/agent-ticket-tracker/pull/10>
- GitHub issue adapter issue：<https://github.com/zinan92/agent-ticket-tracker/issues/11>
- GitHub issue adapter PR：<https://github.com/zinan92/agent-ticket-tracker/pull/12>
- GitHub adapter review follow-up issue：<https://github.com/zinan92/agent-ticket-tracker/issues/13>
- GitHub adapter review follow-up PR：<https://github.com/zinan92/agent-ticket-tracker/pull/14>

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
- `att attach --project <path> --feature auto` 可登记并启动/复用一个 loopback observer；
- `feature=auto` 优先读取 Ask Park state，其次跟随唯一 `.scratch/<feature>` source，最后展示 project artifacts；多个 source fail closed；
- 无 local workflow source 时，可通过已认证 `gh` 只读读取 GitHub open milestones、issues、linked PRs 和 CI checks，并按保守规则投影状态；GitHub 不可用时退回 project artifacts；
- 内部 `agent-ticket-tracker-hook` 已安装到 `/Users/wendy/.codex/skills/agent-ticket-tracker-hook`，全局 Agent 规则要求现有 workflow 入口隐形调用它；
- 没有结构化 source 时，HTML/Markdown/JSON/Git 只作为观察数据，不作为完成状态；
- local Markdown 导入默认产生 `ticket` 节点；Wayfinder `decision` 节点需要 manual manifest，专用 adapter 尚未实现。

## 明确不能做什么

- 不读取实时 Linear 状态或 GitHub review/comment 语义；GitHub adapter 只读取 issues、linked PRs 和 observed CI checks；
- 不解析任意 HTML 语义或由 artifact 存在推断完成；
- 不启动、暂停、重试或合并 Agent 工作；
- 不修改被监控项目的源代码、分支、remote 或凭证；
- 不把 Agent 自报、缺失证据或 stale evidence 变成绿色状态；
- 不注入 Codex App 原生侧边栏。

## 下一步

1. 在一个真实项目上运行 5-ticket pilot，记录 verified-software 与 verified-experience 的差异。
2. 优先增加额外的只读数据源 adapters，例如 Linear、richer review receipts 和 Wayfinder maps。
3. 不把 executor adapter 纳入 tracker 产品契约；执行仍由 `/implement` 等 command 负责。
