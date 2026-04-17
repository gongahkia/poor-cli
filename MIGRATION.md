# poor-cli 6.0 Migration — Noun-First Command Surface

The 6.0 release collapses `poor-cli`'s Neovim plugin and CLI onto a **strict
noun-first** command shape and **deletes every legacy command name** — no
deprecation aliases, no backward-compat shims. This document lists every rename
so you can grep-replace your personal `init.lua`, shell scripts, CI workflows,
and internal docs in a single pass.

## Why

Before 6.0 the plugin registered ~250 commands, including ~104 auto-generated
`PoorCli*` camelcase shims and dozens of `PoorCLI<Noun><Verb>` stacks like
`:PoorCLITaskCreate`, `:PoorCLISessionFork`, `:PoorCLIAcceptWord`. That surface
was unsearchable with `:PoorCLI<Tab>` and forced users to memorize names rather
than learn a small vocabulary of nouns + verbs.

6.0 reduces the Neovim surface to **~29 top-level `:PoorCLI<Noun>` commands**,
each taking a `<verb> [args]` tail that is Tab-completable from a single
source of truth (`lua/poor-cli/command_spec.lua`). The CLI follows the same
shape.

## Nvim plugin — flagship renames

| Old (≤ 5.x)                        | New (6.0)                                |
|------------------------------------|------------------------------------------|
| `:PoorCLITasksPanel`               | `:PoorCLIPanel toggle tasks`             |
| `:PoorCLIAgentsPanel`              | `:PoorCLIPanel toggle agents`            |
| `:PoorCLIHistoryPanel`             | `:PoorCLIPanel toggle history`           |
| `:PoorCLICheckpointsPanel`         | `:PoorCLIPanel toggle checkpoints`       |
| `:PoorCLIQueuePanel`               | `:PoorCLIPanel toggle queue`             |
| `:PoorCLIMemoryPanel`              | `:PoorCLIPanel toggle memory`            |
| `:PoorCLISessionsPanel`            | `:PoorCLIPanel toggle sessions`          |
| `:PoorCLIAutomationsPanel`         | `:PoorCLIPanel toggle automations`       |
| `:PoorCLIPanels open\|close\|toggle` | `:PoorCLIPanel open\|close\|toggle`    |

## Nvim plugin — CRUD families

Every noun-verb stack collapses onto its owning noun. `<ID>` placeholders stay.

| Family    | Old                                | New                                 |
|-----------|------------------------------------|-------------------------------------|
| Task      | `:PoorCLITasks` / `:PoorCLITasksPicker` | `:PoorCLITask list`            |
| Task      | `:PoorCLITaskCreate`               | `:PoorCLITask create`               |
| Task      | `:PoorCLITask{Start,Approve,Cancel,Retry,Replay,Show} <id>` | `:PoorCLITask {start,approve,cancel,retry,replay,show} <id>` |
| Task      | `:PoorCLIInbox`                    | `:PoorCLITask inbox`                |
| Task      | `:PoorCLIRuns`                     | `:PoorCLITask runs`                 |
| Agent     | `:PoorCLIAgents` / `:PoorCLIAgentsPicker` | `:PoorCLIAgent list`         |
| Agent     | `:PoorCLIAgent{Create,Start,Cancel,Logs,Result}` | `:PoorCLIAgent {create,start,cancel,logs,result}` |
| Automation | `:PoorCLIAutomations` / `:PoorCLIAutomationsPicker` | `:PoorCLIAutomation list` |
| Automation | `:PoorCLIAutomation{Create,Enable,Disable,Run,History,Replay}` | `:PoorCLIAutomation {create,enable,disable,run,history,replay}` |
| Session   | `:PoorCLISessions` / `:PoorCLISessionsPicker` | `:PoorCLISession list`      |
| Session   | `:PoorCLISession{Create,Switch,Fork,Destroy,Rename,Save,Restore}` | `:PoorCLISession {create,switch,fork,destroy,rename,save,restore}` |
| Session   | `:PoorCLIBranches`                 | `:PoorCLISession branches`          |
| Memory    | `:PoorCLIMemory` (picker)          | `:PoorCLIMemory list`               |
| Memory    | `:PoorCLIMemory{Save,Search,Delete,Review}` | `:PoorCLIMemory {save,search,delete,review}` |
| Memory    | `:PoorCLIMemoryReview{Accept,Reject,Bulk}` | `:PoorCLIMemory review-{accept,reject,bulk}` |
| Memory    | `:PoorCLIMemory{Expiring,ExpireRun}` | `:PoorCLIMemory {expiring,expire-run}` |
| Memory    | `:PoorCLIMemoryPicker` / `Sort` / `Expire` | `:PoorCLIMemory list` / `sort` / `expire` |
| Checkpoint | `:PoorCLICheckpoints`             | `:PoorCLICheckpoint list`           |
| Checkpoint | `:PoorCLICheckpoint{Create,Preview,Gc}` | `:PoorCLICheckpoint {create,preview,gc}` |
| History   | `:PoorCLIHistory` / `HistorySearch` / `HistoryPicker` | `:PoorCLIHistory list` / `search` |
| History   | `:PoorCLIExportConversation`       | `:PoorCLIHistory export`            |
| Prompt    | `:PoorCLIPromptList` / `Save` / `Load` / `Delete` | `:PoorCLIPrompt {list,save,load,delete}` |
| Prompt    | `:PoorCLIPinsList`                 | `:PoorCLIPrompt pins`               |
| Prompt    | `:PoorCLIPrompts`                  | **deleted alias** — use `:PoorCLIPrompt list` |
| Skill     | `:PoorCLISkills` / `SkillsPicker` / `SkillShow` | `:PoorCLISkill {list,show}` |
| Skill     | `:PoorCLICommands` / `CommandsPicker` / `CommandRun` | `:PoorCLISkill alias-{list,run}` |

## Nvim plugin — inline completion

| Old                          | New                                       |
|------------------------------|-------------------------------------------|
| `:PoorCLIComplete`           | `:PoorCLICompletion trigger`              |
| `:PoorCLIAccept`             | `:PoorCLICompletion accept`               |
| `:PoorCLIAcceptWord`         | `:PoorCLICompletion accept-word`          |
| `:PoorCLIAcceptLine`         | `:PoorCLICompletion accept-line`          |
| `:PoorCLIDismiss`            | `:PoorCLICompletion dismiss`              |
| `:PoorCLIAutoTrigger`        | `:PoorCLICompletion auto-trigger`         |
| `:PoorCLICompletionReason`   | `:PoorCLICompletion reason`               |
| `:PoorCLICompletionToggle`   | `:PoorCLICompletion toggle`               |

## Nvim plugin — chat, review, deploy, diff, search

| Old                          | New                                       |
|------------------------------|-------------------------------------------|
| `:PoorCLIChat`               | `:PoorCLIChat toggle`                     |
| `:PoorCLISend <msg>`         | `:PoorCLIChat send <msg>`                 |
| `:PoorCLIClear`              | `:PoorCLIChat clear`                      |
| `:PoorCLIRetry`              | `:PoorCLIChat retry`                      |
| `:PoorCLIBroke` / `MyTreat`  | `:PoorCLIChat terse` / `rich`             |
| `:PoorCLIQueue` (both dups)  | `:PoorCLIChat queue` / `enqueue`          |
| `:PoorCLIQueueClear`         | `:PoorCLIChat queue-clear`                |
| `:PoorCLIExplain` (visual)   | `:PoorCLIChat explain` (preserves range)  |
| `:PoorCLIRefactor` (visual)  | `:PoorCLIChat refactor` (preserves range) |
| `:PoorCLITest` / `Doc`       | `:PoorCLIChat test` / `doc`               |
| `:PoorCLIExplainDiff`        | `:PoorCLIChat explain-diff`               |
| `:PoorCLIFixFailures`        | `:PoorCLIChat fix-failures`               |
| `:PoorCLIWorkspaceMap`       | `:PoorCLIChat workspace-map`              |
| `:PoorCLIReview`             | `:PoorCLIReview file`                     |
| `:PoorCLIReviewPr <n>`       | `:PoorCLIReview pr <n>`                   |
| `:PoorCLICommit`             | `:PoorCLIReview commit`                   |
| `:PoorCLILint`               | `:PoorCLIReview lint`                     |
| `:PoorCLIDeploy`             | `:PoorCLIDeploy run`                      |
| `:PoorCLIDeploy{Targets,Validate,History}` | `:PoorCLIDeploy {targets,validate,history}` |
| `:PoorCLIPreview{,Start,Stop,Status}` | `:PoorCLIDeploy preview{,-start,-stop,-status}` |
| `:PoorCLIDiff`               | `:PoorCLIDiff compare`                    |
| `:PoorCLIDiffReview`         | `:PoorCLIDiff review`                     |
| `:PoorCLIReviewClose`        | `:PoorCLIDiff close`                      |
| `:PoorCLIDiffLayout`         | `:PoorCLIDiff layout`                     |
| `:PoorCLITimeline{,Cancel}`  | `:PoorCLIDiff timeline{,-cancel}`         |
| `:PoorCLISearch <q>`         | `:PoorCLISearch run <q>`                  |
| `:PoorCLIIndex` / `IndexStats` / `IndexEmbeddings` | `:PoorCLISearch {index,stats,embeddings}` |
| `:PoorCLIWatch`              | `:PoorCLISearch watch`                    |
| `:PoorCLIWatchScan`          | `:PoorCLISearch watch-scan`               |

## Nvim plugin — config, diag, cost, context, trust, provider, workflow

| Old                          | New                                       |
|------------------------------|-------------------------------------------|
| `:PoorCLIConfig` / `ConfigPicker` | `:PoorCLIConfig list`                |
| `:PoorCLIConfigSet <k> <v>`  | `:PoorCLIConfig set <k> <v>`              |
| `:PoorCLIConfigToggle <k>`   | `:PoorCLIConfig toggle <k>`               |
| `:PoorCLIQaToggle`           | `:PoorCLIConfig qa-toggle`                |
| `:PoorCLIExecProfile`        | `:PoorCLIConfig exec-profile`             |
| `:PoorCLIPermissionMode`     | `:PoorCLIConfig permission-mode`          |
| `:PoorCLISandbox`            | `:PoorCLIConfig sandbox`                  |
| `:PoorCLIContextBudget`      | `:PoorCLIConfig context-budget`           |
| `:PoorCLIInstructions` / `Rules` | `:PoorCLIConfig instructions` / `rules` |
| `:PoorCLIInputLog` / `ChatTrace` | `:PoorCLIConfig input-log` / `chat-trace` |
| `:PoorCLIPickerBackend`      | `:PoorCLIConfig picker-backend`           |
| `:PoorCLIPermissions`        | `:PoorCLIConfig permissions-show`         |
| `:PoorCLISetPermissions`     | `:PoorCLIConfig permissions-set`          |
| `:PoorCLIApiKey`             | `:PoorCLIConfig api-key`                  |
| `:PoorCLIApiKeyStatus`       | `:PoorCLIProvider api-key-status`         |
| `:PoorCLIApiKeyPurge`        | `:PoorCLIProvider api-key-purge`          |
| `:PoorCLIStatus`             | `:PoorCLIDiag status`                     |
| `:PoorCLIDoctor`             | `:PoorCLIDiag doctor`                     |
| `:PoorCLIMcp` / `McpHealth`  | `:PoorCLIDiag mcp` / `mcp-health`         |
| `:PoorCLIPolicy`             | `:PoorCLIDiag policy`                     |
| `:PoorCLITools`              | `:PoorCLIDiag tools`                      |
| `:PoorCLIDiagnostics` / `Trouble` / `FixDiagnostics` | `:PoorCLIDiag inline` / `trouble` / `fix` |
| `:PoorCLISandboxStatus`      | `:PoorCLIDiag sandbox-status`             |
| `:PoorCLIDockerSandbox`      | `:PoorCLIDiag docker-sandbox`             |
| `:PoorCLIRecoverySuggestions` | `:PoorCLIDiag recovery`                  |
| `:PoorCLICopyDebugInfo`      | `:PoorCLIDiag debug-copy`                 |
| `:PoorCLIOpenLog` / `OpenStateDir` / `WriteMinInit` | `:PoorCLIDiag log-open` / `state-open` / `write-min-init` |
| `:PoorCLICost`               | `:PoorCLICost show`                       |
| `:PoorCLICostDashboard`      | `:PoorCLICost dashboard`                  |
| `:PoorCLISavings` / `SavingsDashboard` | `:PoorCLICost savings`          |
| `:PoorCLIEconomyPreset`      | `:PoorCLICost economy-preset`             |
| `:PoorCLICostHistory`        | `:PoorCLICost history`                    |
| `:PoorCLITokens` / `CacheStats` | `:PoorCLICost tokens` / `cache-stats` |
| `:PoorCLIBudget`             | `:PoorCLICost budget`                     |
| `:PoorCLICompareCost`        | `:PoorCLICost compare`                    |
| `:PoorCLIExportCost`         | `:PoorCLICost export`                     |
| `:PoorCLIEstimateCost`       | `:PoorCLICost estimate`                   |
| `:PoorCLIPressure` / `Breakdown` | `:PoorCLICost pressure` / `breakdown` |
| `:PoorCLIContext`            | `:PoorCLIContext show`                    |
| `:PoorCLIContextPreview`     | `:PoorCLIContext preview`                 |
| `:PoorCLIContextCompact` / `Compact` | `:PoorCLIContext compact` / `compact-strategy` |
| `:PoorCLIMutationPreview`    | `:PoorCLIContext mutation-preview`        |
| `:PoorCLIRepoMap`            | `:PoorCLIContext repo-map`                |
| `:PoorCLITrust`              | `:PoorCLITrust show`                      |
| `:PoorCLITrustCenter` / `TrustStatus` | `:PoorCLITrust center`           |
| `:PoorCLITrustRepo` / `UntrustRepo` | `:PoorCLITrust repo` / `untrust-repo` |
| `:PoorCLIProviders` / `ProvidersPicker` | `:PoorCLIProvider list`       |
| `:PoorCLIProviderInfo`       | `:PoorCLIProvider info`                   |
| `:PoorCLISwitchProvider` / `Switch` | `:PoorCLIProvider switch`          |
| `:PoorCLIProviderCompare`    | `:PoorCLIProvider compare`                |
| `:PoorCLIOllamaModels`       | `:PoorCLIProvider ollama`                 |
| `:PoorCLIWorkflows` / `Workflow` | `:PoorCLIWorkflow list` / `show`      |
| `:PoorCLIStrategies`         | `:PoorCLIWorkflow strategies`             |
| `:PoorCLIRerankerStrategy`   | `:PoorCLIWorkflow reranker`               |
| `:PoorCLIAdaptivePruning`    | `:PoorCLIWorkflow adaptive-pruning`       |
| `:PoorCLIProfiles` / `ApplyProfile` | `:PoorCLIProfile list` / `apply`   |

## Nvim plugin — server, help, audit, misc

| Old                          | New                                       |
|------------------------------|-------------------------------------------|
| `:PoorCLIStart` / `Stop` / `Restart` / `Cancel` | `:PoorCLIServer {start,stop,restart,cancel}` |
| `:PoorCLIHelp`               | `:PoorCLIHelp commands`                   |
| `:PoorCLIHome`               | `:PoorCLIHelp home`                       |
| `:PoorCLIPalette`            | `:PoorCLIHelp palette`                    |
| `:PoorCLIOnboarding`         | `:PoorCLIHelp onboarding`                 |
| `:PoorCLIAuditExport`        | `:PoorCLIAudit export`                    |
| `:PoorCLIPlan` / `PlanBoard` | `:PoorCLIPlan open`                       |
| `:PoorCLIService`            | `:PoorCLIService {start,stop,status,logs}` |
| `:PoorCLIExport`             | `:PoorCLIHistory export-fmt`              |

## Nvim plugin — camelcase shims

The auto-generated `PoorCli*` shim loop (e.g. `:PoorCliAccept`,
`:PoorCliTasksPanel`, `:PoorCliChatTrace`, …) is **deleted in full**. ~104
commands disappear as one change. If your config referenced any `PoorCli*`
name, switch to the `PoorCLI<Noun> <verb>` form above.

## CLI — renames

Most CLI commands already followed a noun-verb subcommand shape and did **not**
change. Only these outliers moved:

| Old                               | New                                   |
|-----------------------------------|---------------------------------------|
| `poor-cli doctor`                 | `poor-cli diag doctor`                |
| `poor-cli status`                 | `poor-cli diag status`                |
| `poor-cli policy`                 | `poor-cli diag policy`                |
| `poor-cli tools`                  | `poor-cli diag tools`                 |
| `poor-cli mcp`                    | `poor-cli diag mcp`                   |
| `poor-cli review-pr <n>`          | `poor-cli pr review <n>`              |
| `poor-cli github-task create ...` | `poor-cli pr task create ...`         |
| `poor-cli skills {list,show,run}` | `poor-cli skill {list,show,run}`      |
| `poor-cli commands {list,show,run}` | `poor-cli skill alias-{list,show,run}` |
| `poor-cli install-info`           | `poor-cli install info`               |
| `poor-cli watch`                  | `poor-cli search watch`               |
| `poor-cli deploy [flags]`         | `poor-cli deploy run [flags]`         |
| `poor-cli preview [flags]`        | `poor-cli deploy preview [flags]`     |
| `poor-cli cost pressure`          | `poor-cli context pressure`           |
| `poor-cli cost breakdown`         | `poor-cli context breakdown`          |

`poor-cli github-task` is invoked by `.github/workflows/tests.yml`. Update any
forks/CI recipes alongside this migration.

## Migration recipe — sed

For a user `init.lua` that peppers old names, this rewrites the most common:

```bash
# Nvim plugin renames — run once against your init.lua or config files.
sed -i.bak \
  -e 's/:PoorCLITasksPanel/:PoorCLIPanel toggle tasks/g' \
  -e 's/:PoorCLIAgentsPanel/:PoorCLIPanel toggle agents/g' \
  -e 's/:PoorCLIAccept\b/:PoorCLICompletion accept/g' \
  -e 's/:PoorCLIAcceptWord/:PoorCLICompletion accept-word/g' \
  -e 's/:PoorCLIAcceptLine/:PoorCLICompletion accept-line/g' \
  -e 's/:PoorCLIDismiss/:PoorCLICompletion dismiss/g' \
  -e 's/:PoorCLIComplete\b/:PoorCLICompletion trigger/g' \
  -e 's/:PoorCLIChat\b/:PoorCLIChat toggle/g' \
  -e 's/:PoorCLIDoctor\b/:PoorCLIDiag doctor/g' \
  -e 's/:PoorCLIStatus\b/:PoorCLIDiag status/g' \
  -e 's/:PoorCLIPalette/:PoorCLIHelp palette/g' \
  -e 's/:PoorCLIHome/:PoorCLIHelp home/g' \
  -e 's/:PoorCLITaskCreate/:PoorCLITask create/g' \
  -e 's/:PoorCLISessionFork/:PoorCLISession fork/g' \
  your-init.lua

# CI workflow renames (adjust paths as needed).
sed -i.bak \
  -e 's/poor-cli doctor/poor-cli diag doctor/g' \
  -e 's/poor-cli review-pr/poor-cli pr review/g' \
  -e 's/poor-cli github-task/poor-cli pr task/g' \
  -e 's/poor-cli skills/poor-cli skill/g' \
  .github/workflows/*.yml
```

The full rename table above is the authoritative reference — the sed recipe is
a starting point, not exhaustive.

## 6.1 removals — UX consolidation

The 6.1 release removes five duplicate read-only scratch pages, one redundant
inline-completion keymap, and the legacy `vsplit` panel mode. No backward-compat
aliases. Update any references to:

| Removed (≤ 6.0)                        | Replacement                                |
|----------------------------------------|--------------------------------------------|
| `:PoorCLIHelp commands`                | `:PoorCLIHelp palette` (fuzzy)             |
| `:PoorCLITrust show`                   | `:PoorCLITrust center`                     |
| `:PoorCLIConfig permissions-show`      | `:PoorCLITrust center` (permission section)|
| `:PoorCLIChat workspace-map`           | `:PoorCLIContext repo-map` (real float)    |
| `<M-?>` completion preview split       | `<M-]>`/`<M-[>` cycle + ghost text         |
| `config.layout.panels = "vsplit"`      | (removed — all panels are floats)          |
| `config.layout.scratch = "vsplit"`     | (removed — all scratch surfaces are floats)|
| `config.preview_key`                   | (removed)                                  |

The Python-side `/workspace-map` slash command is unchanged and still works as
`:PoorCLIChat send /workspace-map` if you need it.

## Verification after migrating

- Nvim: run `:PoorCLI<Tab>`. You should see ≤29 top-level commands and **no**
  `PoorCli*` camelcase ones.
- Nvim: run `:PoorCLIPanel toggle <Tab><Tab>` and confirm the 8 panel names
  complete.
- CLI: run `poor-cli help` and confirm the top-level noun list matches the
  "Diagnostics / Code review / Reuse" sections above.
- CLI: `poor-cli diag doctor`, `poor-cli pr review 1`, `poor-cli install info`,
  `poor-cli skill list` each produce the same output as their pre-6.0
  counterparts.
