<div align="center">

# Agent Ticket Tracker

**把长时间的 Agent 开发，变成一张可监控、可核验、可只读唤醒的交付地图。**

[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-16794C.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-MVP-B77820.svg)](https://github.com/zinan92/agent-ticket-tracker/issues/1)

</div>

---

```text
in  project path + feature slug + local artifacts, Git metadata, or an explicit manifest
out map-first delivery view + node evidence + blocker frontier + safe wake brief

fail missing/malformed/stale source → show the failure and produce no actionable frontier
fail unverified green claim       → downgrade the node and require current evidence
fail unsafe project path          → reject before reading or writing state
fail wake                         → report the blocker without dispatching an Agent
```

## 这是什么

Agent Ticket Tracker 是一个本地 read-only delivery observer/dashboard 的 MVP。它不是 Codex App 的原生插件，也不是新的 Agent harness。它把项目已有的 spec、tickets、阻塞关系、回执和可读的项目活动信号，整理成一个可以持续查看的全貌地图。

它服务于这条常用链路：

```text
Ask Matt
  → Setup Matt Pocock skills
  → grill-with-docs
  → to-spec
  → to-tickets
  → Agent implement
  → review / test / device evidence
  → merge
```

Tracker 只观察和报告。它不会替你创建 Issue、启动 Agent、修改代码、切分支、创建 PR、合并，或改变任何 command 的执行状态。所有状态变化仍由原有 workflow command 负责，例如 `/implement`。

## 示例输出

初始化一个不会接触真实项目的样例：

```bash
PYTHONPATH=src python3 -m agent_ticket_tracker init \
  --project /tmp/my-project \
  --feature demo \
  --sample
```

```text
created=/tmp/my-project/.agent-ticket-tracker/demo/manifest.json
source=sample
```

唤醒只读检查：

```bash
PYTHONPATH=src python3 -m agent_ticket_tracker wake \
  --project /tmp/my-project \
  --feature demo
```

```text
Source: sample
Frontier:
- none
Blockers:
- ticket-workbench: Workbench evidence [needs-review] -> Re-run the missing device check
Next brief:
Sample state is for UI review only. Do not dispatch work from it.
Exit:
valid-sample
```

运行后，浏览器显示 map-first 交付地图和“最近观察”只读 feed。点击节点会打开右侧详情层，地图不会消失；详情包含状态、完成比例、验收项、证据、阻塞关系和下一步。

## 快速开始

```bash
git clone https://github.com/zinan92/agent-ticket-tracker.git
cd agent-ticket-tracker

# 不安装依赖也可以直接运行
export PYTHONPATH=src

# 在实际项目中初始化一个 feature run
python3 -m agent_ticket_tracker init \
  --project /absolute/path/to/your-project \
  --feature my-feature

# 启动本地控制台
python3 -m agent_ticket_tracker serve \
  --project /absolute/path/to/your-project \
  --feature my-feature
```

命令会打印 localhost URL。把这个 URL 打开到 Codex App 的浏览器面板即可。

默认状态文件位于：

```text
/absolute/path/to/your-project/.agent-ticket-tracker/my-feature/manifest.json
```

## 你现在的使用方法

### 1. Ask Matt

先让 Ask Matt 判断最终交付属于哪个业务域，以及应该走 Use 还是 Build。

### 2. Setup Matt Pocock skills

在真实工程目录中完成一次 repo 配置，让 `to-spec` 和 `to-tickets` 知道 spec、issue tracker、domain docs 在哪里。

### 3. grill-with-docs

让它澄清意图，并把决策写入 `CONTEXT.md`、ADR 或对应项目文档。

### 4. to-spec

把已经讨论过的内容冻结成 spec。不要在 Tracker 中重新解释产品目标。

### 5. to-tickets

把 spec 切成独立的 vertical-slice tickets，并写出每张 ticket 的 `Blocked by`。

### 6. init

Ticket 文件准备好之后，在被监控的真实项目中执行：

```bash
PYTHONPATH=/absolute/path/to/agent-ticket-tracker/src \
python3 -m agent_ticket_tracker init \
  --project /absolute/path/to/your-project \
  --feature my-feature
```

如果项目使用本地 Markdown tracker，MVP 会读取固定位置：

```text
<project>/.scratch/<feature>/spec.md
<project>/.scratch/<feature>/issues/NN-slug.md
```

`init` 只创建 `.agent-ticket-tracker/<feature>/manifest.json`，不会修改项目源代码、分支、remote 或现有 ticket。

### 7. serve

```bash
PYTHONPATH=src python3 -m agent_ticket_tracker serve \
  --project /absolute/path/to/your-project \
  --feature my-feature
```

这是一个 loopback-only 本地服务。页面每两秒重新读取状态，适合在 Agent 长时间运行时放在 Codex App 旁边观察。

### 8. implement

继续使用现有 `/implement` 执行单张 ticket。Tracker 不替换它，也不会偷偷替它修改验收标准。

### 9. wake：唤醒观察器

当 Agent 停止、上下文被清理、机器重启，或者你隔了一段时间回来时，执行：

```bash
PYTHONPATH=src python3 -m agent_ticket_tracker wake \
  --project /absolute/path/to/your-project \
  --feature my-feature
```

命令会重新读取 manifest、spec、tickets 以及可读的项目/Git 活动，并输出当前观察摘要。它不会自动启动 Agent；如果你要继续开发，仍然由你调用 `/implement` 或其他执行 command。

这里的“唤醒”只表示唤醒 tracker 重新观察，不表示改变开发流程。

## Wayfinder 怎么接

Wayfinder 产生的是 decision tickets，而不是直接的实现 tickets。Tracker 的统一节点模型支持：

```text
kind=decision  → 继续调查和消除不确定性
kind=ticket    → 进入实现和验收
```

MVP 先保留这两个语义，不把 Wayfinder 改写成普通开发任务。当前 local Markdown 导入默认生成 `ticket` 节点；需要 `decision` 节点时可使用 manual manifest。未来接入 Wayfinder 的 map 文件时，decision 节点会进入同一张 Delivery Map。

## 状态语义

```text
planned       已记录，尚未准备执行
ready         可以开始，但还没有执行
running       有执行活动，但未完成
partial       一部分验收已经完成
verified      验收项全部完成，并且有当前 verified evidence
needs-review  发现不一致、证据不足或需要复核
blocked       被明确的 blocker 卡住
waiting       尚未满足开始条件
```

绿色不是 Agent 自己填写的装饰。一个节点只有在以下条件同时满足时才会变成 `verified`：

1. 至少存在一条 acceptance record；
2. 所有 acceptance record 都是 `verified`；
3. 至少存在一条当前的 verified evidence；
4. 所有 blocker 都已经是 `verified`。

软件测试、云端状态、体验验证和设备验证应当分开记录。缺失的证据保持缺失，不用推测补齐。

## Manifest v1

```json
{
  "schemaVersion": 1,
  "run": {
    "id": "my-feature",
    "displayName": "My feature",
    "featureSlug": "my-feature"
  },
  "source": {
    "kind": "local_markdown",
    "root": ".scratch/my-feature",
    "spec": "spec.md",
    "issues": "issues",
    "observedAt": "2026-08-27T09:00:00Z",
    "maxAgeSeconds": 900
  },
  "nodes": [],
  "overrides": {}
}
```

支持三种 source：

- `sample`：只用于体验 UI，不产生 frontier；
- `manual`：节点完全由 manifest 提供；
- `local_markdown`：固定读取项目 `.scratch/<feature>/spec.md` 和 `issues/`，每次读取时在内存中生成节点。

`overrides` 只能补充 acceptance、evidence、nextAction 和 note，不能直接把节点改成绿色。

`/api/state` 另外返回 derived `observations`。它们来自读取时的文件/Git 信号，不写入 manifest，也不覆盖节点 status、acceptance、evidence、blocker 或 frontier。

## 架构

```text
┌────────────────────────────┐
│ Project artifacts           │
│ spec / tickets / receipts  │
└──────────────┬─────────────┘
               │ read-only
               ▼
┌────────────────────────────┐
│ Normalizer                 │
│ schema / source / status   │
│ blocker / frontier rules  │
└───────────┬─────────┬──────┘
            │         │
            ▼         ▼
┌────────────────┐  ┌────────────────┐
│ Local HTTP UI  │  │ Read-only feed │
│ map + evidence │  │ next action    │
└────────────────┘  └────────────────┘
```

## HTTP endpoints

The local server binds to `127.0.0.1` only:

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Packaged map-first UI |
| `GET` | `/api/state` | Normalized run state as JSON |
| `GET` | `/healthz` | Local process health |

No endpoint serves arbitrary files from the monitored project.

## 项目结构

```text
agent-ticket-tracker/
├── src/agent_ticket_tracker/
│   ├── cli.py                 # init, serve, wake
│   ├── core.py                # manifest and frontier truth rules
│   ├── server.py              # loopback-only HTTP server
│   └── web/index.tmpl         # map-first UI
├── tests/                     # stdlib unittest suite
├── docs/superpowers/specs/    # design and contract decisions
├── .scratch/                  # this repo's local issue contract
├── AGENTS.md
├── LICENSE
└── pyproject.toml
```

## For AI Agents

```yaml
name: agent-ticket-tracker
version: 0.1.0
capability:
  summary: "Read an explicit local delivery state and produce a map, evidence view, activity feed, and read-only wake brief."
  in: "project path, feature slug, local Markdown artifacts, or manifest v1"
  out: "normalized delivery state, observations, frontier, blockers, and read-only brief"
  fail:
    - "missing source -> show missing and produce no frontier"
    - "malformed manifest -> show malformed and stop normalization"
    - "stale source or evidence -> keep it visible and non-green"
    - "unsafe path -> reject before reading or writing"
  adapters:
    - "local_markdown"
    - "manual_manifest"
    - "local_git_observer"
cli_command: "python3 -m agent_ticket_tracker"
cli_args:
  - name: "--project"
    type: "path"
    required: true
    description: "Existing monitored project directory"
  - name: "--feature"
    type: "string"
    required: true
    description: "Lowercase feature slug"
cli_flags:
  - name: "init"
    description: "Create a non-overwriting project-local manifest"
  - name: "serve"
    description: "Serve the read-only local observer on loopback"
  - name: "wake"
    description: "Print Source, Frontier, Blockers, Observations, Next brief, and Exit without dispatch"
health_check: "GET http://127.0.0.1:<port>/healthz"
```

### Agent invocation example

```bash
PYTHONPATH=/absolute/path/to/agent-ticket-tracker/src \
python3 -m agent_ticket_tracker wake \
  --project /absolute/path/to/project \
  --feature feature-slug
```

An Agent should treat `Source`, `Frontier`, and `Blockers` as observations. It should not claim that a node is complete unless the relevant evidence is present and current.

## Can do now / Cannot do now / Next phase

### Can do now

- Read local Markdown ticket artifacts or an explicit manifest;
- observe local artifact and Git activity without changing it;
- show the full map, node evidence, and observation feed on localhost;
- calculate blockers and the actionable frontier conservatively;
- print a copyable wake brief for a fresh Agent context.

### Cannot do now

- Read live GitHub or Linear state;
- create or merge issues and pull requests;
- launch, pause, retry, or steer an Agent;
- prove device, cloud, or user experience acceptance from a local test alone;
- inject a native sidebar into the Codex App.

### Next phase

Add narrowly-scoped read-only adapters for additional sources such as GitHub, Linear, PRs, and receipts. Executor adapters are not part of this product contract.

## Development

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m agent_ticket_tracker --help
```

The repository's first MVP contract is tracked in [Issue #1](https://github.com/zinan92/agent-ticket-tracker/issues/1); the read-only observation follow-up is [Issue #3](https://github.com/zinan92/agent-ticket-tracker/issues/3). The current implementation is local-only and deliberately does not update the GitHub profile automatically.

## License

MIT. See [LICENSE](LICENSE).
