-- Wok full init.lua example
-- Place at ~/.config/wok/init.lua

wok.theme.set({
    background = "#1e1e2e",
    foreground = "#cdd6f4",
    cursor = "#f5e0dc",
})

wok.bind_key("terminal", "ctrl+shift+t", "new_tab")
wok.bind_key("terminal", "ctrl+shift+w", "close_tab")
wok.bind_key("terminal", "ctrl+d", "split_vertical")
wok.bind_key("terminal", "ctrl+shift+d", "split_horizontal")
wok.bind_key("terminal", "ctrl+f", "search_global")

wok.register_command("save_work", "save_session:work")
wok.register_command("load_work", "load_session:work")
wok.bind_key("terminal", "ctrl+shift+s", "save_work")
wok.bind_key("terminal", "ctrl+shift+r", "load_work")

wok.on("app_start", function()
    wok.notify("Wok started")
end)

wok.on("block_finished", function(event)
    if event.exit_code ~= 0 then
        wok.notify("Command failed: " .. event.command)
    end
end)

wok.on("cwd_changed", function(event)
    wok.notify("Working directory changed to " .. event.path)
end)
