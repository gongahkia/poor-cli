# CLI Coding Agent Workflows

Wok does not bundle an AI agent or route work through a cloud service. The integration model is to treat tools such as Claude Code, Codex, ADA, Copilot CLI, and Gemini CLI as ordinary local commands, then add terminal-native structure around them: workflows, blocks, command telemetry, hooks, and completion notifications.

## What Wok Can Own

- Launch repeatable agent commands from the command palette via workflows.
- Keep each agent run in a navigable command block with duration and exit status.
- Notify when a long-running agent command, pane, or tab finishes.
- Use Lua hooks to route agent-specific behavior without hard-coding one vendor.
- Use `command_telemetry = true` when you need local JSONL timing data for command performance.

Wok should not own credentials, model selection, or provider-specific auth. Keep that in each vendor CLI.

## Agent Workflows

Add workflows in `~/.config/wok/init.lua` or TOML files under `~/.config/wok/workflows/`.

```lua
wok.register_workflow({
    name = "agent: codex implement",
    description = "Ask Codex CLI to implement a scoped task in the current repo",
    template = "codex \"${task}\"",
    params = {
        { name = "task", placeholder = "Describe the change" },
    },
})

wok.register_workflow({
    name = "agent: claude review",
    description = "Ask Claude Code to review the current working tree",
    template = "claude \"review the current changes for bugs, regressions, and missing tests\"",
})

wok.register_workflow({
    name = "agent: gemini explain",
    description = "Ask Gemini CLI a repo-local question",
    template = "gemini \"${question}\"",
    params = {
        { name = "question", placeholder = "What should Gemini inspect?" },
    },
})

wok.register_workflow({
    name = "agent: copilot suggest",
    description = "Use GitHub Copilot CLI for a shell suggestion",
    template = "gh copilot suggest \"${prompt}\"",
    params = {
        { name = "prompt", placeholder = "Shell task" },
    },
})

wok.register_workflow({
    name = "agent: ada task",
    description = "Run an ADA CLI task; adjust the binary name and flags to your install",
    template = "ada \"${task}\"",
    params = {
        { name = "task", placeholder = "Describe the task" },
    },
})
```

Open the command palette and filter with `@agent:` to select these workflows.

## Completion Notifications

Use `block_finished` for command-level notifications. This is usually the right hook for CLI agents because it fires when the shell integration detects command completion and includes duration and exit code.

```lua
local function starts_with_agent(command)
    local cmd = string.lower(command or "")
    return cmd:match("^%s*claude[%s%c]") ~= nil
        or cmd:match("^%s*codex[%s%c]") ~= nil
        or cmd:match("^%s*gemini[%s%c]") ~= nil
        or cmd:match("^%s*gh%s+copilot[%s%c]") ~= nil
        or cmd:match("^%s*ada[%s%c]") ~= nil
end

wok.on("block_finished", function(event)
    if not starts_with_agent(event.command) then
        return
    end

    local exit_code = event.exit_code or 0
    local status = exit_code == 0 and "finished" or ("failed: " .. tostring(exit_code))
    wok.system_notify({
        title = "Agent " .. status,
        subtitle = event.tab_title or ("pane " .. tostring(event.pane_id)),
        message = event.command or "agent command",
    })
end)
```

Use `pane_exited` or `tab_done` when the thing you care about is a whole terminal or tab lifecycle, not a single command.

```lua
wok.on("tab_done", function(event)
    wok.system_notify({
        title = "Wok tab done",
        subtitle = event.tab_title or ("tab " .. tostring(event.tab_index)),
        message = tostring(event.pane_count or 0) .. " pane(s) exited",
    })
end)
```

## Recommended Layouts

- One agent per tab: simple review of each run, easiest notification routing.
- Agent plus test split: left pane runs the agent, right pane runs `cargo test`, `npm test`, or project-specific checks.
- Broadcast mode for setup only: useful for installing dependencies or checking versions across panes, less useful for interactive agent sessions.
- Save named sessions for repeated repo workflows, then use agent workflows inside the restored workspace.

## Performance Notes

For performance debugging, enable:

```toml
debug_overlay = true
command_telemetry = true
```

Command telemetry is written to `~/.config/wok/command-telemetry.jsonl`. It includes command text, cwd, exit code, and duration, so keep it disabled for secret-bearing workflows.
