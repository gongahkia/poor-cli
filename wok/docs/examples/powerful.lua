-- Wok "powerful" init.lua — exercises the full API surface.
-- Place at ~/.config/wok/init.lua

-- 1. Theme + status bar customisation
wok.theme.set({
    background = "#1e1e2e",
    foreground = "#cdd6f4",
    cursor     = "#f5e0dc",
})

wok.status_bar.set_left({
    { text = "wok", color = "#89b4fa" },
})
wok.status_bar.set_refresh_interval(2000) -- 2s

-- 2. Custom keybindings + chord-style command aliases
wok.bind_key("terminal", "cmd+shift+t", "new_tab")
wok.bind_key("terminal", "cmd+shift+w", "close_tab")
wok.bind_key("terminal", "cmd+d",       "split_vertical")
wok.bind_key("terminal", "cmd+shift+d", "split_horizontal")
wok.bind_key("terminal", "cmd+f",       "search_global")
wok.bind_key("terminal", "cmd+shift+p", "command_palette")

-- 3. Lifecycle hooks: greet on start, alert on failure, log every cwd change
wok.on("app_start", function()
    local h = wok.history.entries()
    wok.notify("Wok started — " .. #h .. " history entries available")
end)

wok.on("block_finished", function(event)
    if event.exit_code ~= 0 then
        wok.system_notify({
            title    = "Command failed",
            subtitle = "exit " .. tostring(event.exit_code),
            message  = event.command,
        })
    end
end)

local cwd_log_path = "cwd-log.txt"
wok.on("cwd_changed", function(event)
    if not wok.fs.exists(cwd_log_path) then
        wok.fs.write(cwd_log_path, "")
    end
    local prev = wok.fs.read(cwd_log_path)
    wok.fs.write(cwd_log_path, prev .. os.date("%H:%M:%S ") .. event.path .. "\n")
end)

-- 4. Triggers: highlight git push output + notify when CI agents finish
wok.add_trigger("ci agent finished", "^\\s*(claude|codex|gemini|gh\\s+copilot)", {
    "highlight_cyan",
    "system_notify:CI agent command finished",
})

-- 5. Custom commands the user can run from the palette / via wok.action
wok.register_command("backup_history", function()
    local entries = wok.history.entries()
    local lines = {}
    for _, e in ipairs(entries) do
        table.insert(lines, e.command)
    end
    local payload = table.concat(lines, "\n")
    wok.fs.write("history-backup.txt", payload)
    wok.notify("Backed up " .. #entries .. " history entries")
end)

wok.register_command("clean_failed_blocks", function()
    local n = 0
    for _, b in ipairs(wok.blocks.list()) do
        if b.exit_code and b.exit_code ~= 0 then
            n = n + 1
        end
    end
    wok.notify("Found " .. n .. " failed blocks in the active pane")
end)

-- 6. Pane / tab / window control
wok.register_command("focus_zen_mode", function()
    wok.window.set_opacity(0.96)
    wok.window.set_title("zen")
    -- Close every pane except the active one
    while wok.workspace().pane_count > 1 do
        wok.panes.close()
    end
end)

wok.bind_key("terminal", "cmd+shift+z", "focus_zen_mode")

-- 7. Clipboard — copy the last block's output into an analysis buffer
wok.register_command("yank_last_output", function()
    local blocks = wok.blocks.list()
    local last = blocks[#blocks]
    if not last then
        wok.notify("No blocks to yank")
        return
    end
    -- Compose a header + command for context; output text comes from the
    -- terminal grid which Lua doesn't read directly today.
    local payload = string.format(
        "$ %s\n[exit %s]\n",
        last.command,
        tostring(last.exit_code)
    )
    wok.clipboard.copy(payload)
    wok.notify("Copied last block header to clipboard")
end)

-- 8. Inject input into the active pane's PTY (e.g. auto-respond to prompts)
wok.register_command("send_yes", function()
    wok.pane_api.send_input("y\r")
end)

-- 9. Workflow registration (user-callable parameter-filled commands)
wok.register_workflow({
    name = "git: commit message",
    description = "Run git commit -m '<message>'",
    parameters = {
        { name = "message", description = "Commit message", required = true },
    },
    command = "git commit -m \"{message}\"",
})

-- 10. Periodic timer — refresh status bar with current branch
wok.set_interval(15000, function()
    -- this is fired off the main thread; the simplest indicator is to call
    -- `wok.exec` and let the user's shell push the data, but we can also use
    -- the snapshot for cheap state.
    local pane = wok.pane()
    if pane and pane.cwd then
        wok.status_bar.set_right({
            { text = pane.cwd:gsub(os.getenv("HOME") or "", "~"), color = "#a6e3a1" },
        })
    end
end)

-- 11. wok.setup integration (run wok doctor on demand from a hotkey)
wok.register_command("doctor", function()
    wok.setup.doctor({ json = false })
end)
wok.bind_key("terminal", "cmd+shift+h", "doctor")
