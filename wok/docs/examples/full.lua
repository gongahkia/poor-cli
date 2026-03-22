-- Walk full init.lua example
-- Place at ~/.config/walk/init.lua

walk.theme.set({
    background = "#1e1e2e",
    foreground = "#cdd6f4",
    cursor = "#f5e0dc",
})

walk.bind_key("terminal", "ctrl+shift+t", "new_tab")
walk.bind_key("terminal", "ctrl+shift+w", "close_tab")
walk.bind_key("terminal", "ctrl+d", "split_vertical")
walk.bind_key("terminal", "ctrl+shift+d", "split_horizontal")
walk.bind_key("terminal", "ctrl+f", "search_global")

walk.register_command("save_work", "save_session:work")
walk.register_command("load_work", "load_session:work")
walk.bind_key("terminal", "ctrl+shift+s", "save_work")
walk.bind_key("terminal", "ctrl+shift+r", "load_work")

walk.on("app_start", function()
    walk.notify("Walk started")
end)

walk.on("block_finished", function()
    walk.notify("Command block finished")
end)

walk.on("cwd_changed", function()
    walk.notify("Working directory changed")
end)
