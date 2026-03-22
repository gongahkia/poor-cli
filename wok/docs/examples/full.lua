-- Walk full init.lua example
-- Place at ~/.config/walk/init.lua

-- Theme configuration
walk.theme.set({
    background = "#1e1e2e",
    foreground = "#cdd6f4",
    cursor = "#f5e0dc",
})

-- Custom keybindings
walk.keymap("normal", "ctrl+shift+t", "new_tab")
walk.keymap("normal", "ctrl+shift+w", "close_tab")
walk.keymap("normal", "ctrl+shift+d", "split_horizontal")
walk.keymap("normal", "ctrl+d", "split_vertical")

-- Event hooks
walk.on("command_finished", function(e)
    if e.exit_code ~= 0 then
        walk.notify("Command failed with exit code " .. e.exit_code)
    end
end)

walk.on("directory_changed", function(e)
    -- Update window title with CWD
end)
