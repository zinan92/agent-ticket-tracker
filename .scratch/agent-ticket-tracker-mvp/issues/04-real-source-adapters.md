# 04 - Real source adapters

**Status:** claimed

**GitHub issue:** #7

## Outcome

让 Tracker 在真实项目没有 `.scratch/<feature>` 时仍然显示真实过程数据：优先读取 `.ask-park/state.json`，否则展示项目级 HTML/Markdown/JSON/Git 活动；dashboard 不再因为 source 格式不同而空白。

## Acceptance criteria

- [ ] `feature=auto` 优先只读读取合法 `.ask-park/state.json`，投影 project/current module/六个 module activity 与 evidence。
- [ ] 没有 Ask Park state 但项目存在 HTML、Markdown、JSON 或 Git 活动时，返回 project-observation live state 和真实活动摘要；artifact 不被解释成完成。
- [ ] auto 无 source 时显示“未发现结构化 workflow source”与真实 Git/artifact observations，不产生伪造 frontier。
- [ ] malformed state、source 歧义、不安全 symlink 或读取失败时 fail closed；不执行、不修改、不把数据变绿。
- [ ] `59276` 与 `49681` 两个真实 observer 重启到新版本后都能显示真实数据；一个显示 Ask Park module 节点，另一个显示 trading HTML/Git/artifact observations。
- [ ] 测试、gitleaks、HTTP smoke 和 browser DOM debug 通过。

## In scope

- Ask Park state v1 read-only adapter。
- Project artifact fallback and non-empty dashboard projection。
- Auto source priority and source diagnostics。
- Observer restart safety needed to validate the two live pages。

## Out of scope

- 修改任何项目的 state、代码、ticket、branch、PR 或 receipt。
- 解析任意 HTML 语义、推断开发完成、创建 frontier 或调用 `/implement`。
- GitHub/Linear API、executor、retry/pause/resume、Codex native UI。

## 禁区

Tracker 只能读取已存在的数据并投影展示；HTML 存在不等于完成，缺失证据不等于绿色，adapter 失败必须可见且无副作用。
