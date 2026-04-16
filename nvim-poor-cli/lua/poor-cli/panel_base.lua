-- poor-cli/panel_base.lua
-- Shared primitives for info panels (tasks, agents, history, etc.).
-- Mode "float" (default) uses float_win; mode "vsplit" keeps the legacy sidebar.
-- Caller can pin a mode via opts.mode, otherwise we read config.layout.panels.

local M = {}

local function resolve_mode(opt_mode)
    if opt_mode == "float" or opt_mode == "vsplit" then
        return opt_mode
    end
    local ok, cfg = pcall(require, "poor-cli.config")
    if ok and cfg and cfg.config and cfg.config.layout and cfg.config.layout.panels then
        local m = cfg.config.layout.panels
        if m == "float" or m == "vsplit" then return m end
    end
    return "float"
end

function M.new_panel(opts)
    local panel = {
        buf = nil,
        win = nil,
        name = opts.name or "[poor-cli panel]",
        width = opts.width or 60,
        height = opts.height,
        filetype = opts.filetype or "markdown",
        render = opts.render or function() return {} end,
        on_refresh = opts.on_refresh,
        keymaps = opts.keymaps or {},
        events = opts.events or {},
        mode = opts.mode,
    }

    function panel.refresh()
        if not panel.buf or not vim.api.nvim_buf_is_valid(panel.buf) then
            return
        end
        local function render_now()
            local lines = panel.render()
            if type(lines) ~= "table" then lines = {} end
            vim.bo[panel.buf].modifiable = true
            vim.api.nvim_buf_set_lines(panel.buf, 0, -1, false, lines)
            vim.bo[panel.buf].modifiable = false
        end
        if panel.on_refresh then
            panel.on_refresh(render_now)
        else
            render_now()
        end
    end

    function panel.close()
        if panel.win and vim.api.nvim_win_is_valid(panel.win) then
            vim.api.nvim_win_close(panel.win, true)
        end
        panel.win = nil
    end

    function panel.open()
        if panel.win and vim.api.nvim_win_is_valid(panel.win) then
            vim.api.nvim_set_current_win(panel.win)
            panel.refresh()
            return
        end
        if not panel.buf or not vim.api.nvim_buf_is_valid(panel.buf) then
            panel.buf = vim.api.nvim_create_buf(false, true)
            vim.bo[panel.buf].buftype = "nofile"
            vim.bo[panel.buf].bufhidden = "hide"
            vim.bo[panel.buf].swapfile = false
            vim.bo[panel.buf].filetype = panel.filetype
            vim.api.nvim_buf_set_name(panel.buf, panel.name)
        end

        local mode = resolve_mode(panel.mode)
        if mode == "float" then
            local float_win = require("poor-cli.float_win")
            local height = panel.height or math.floor(vim.o.lines * 0.7)
            panel.win = float_win.open(panel.buf, {
                width = panel.width,
                height = height,
                position = opts.position or "center",
                title = " " .. panel.name:gsub("^%[", ""):gsub("%]$", "") .. " ",
                close_keys = {},
                signcolumn = "no",
            })
        else
            vim.cmd("botright " .. panel.width .. "vsplit")
            panel.win = vim.api.nvim_get_current_win()
            vim.api.nvim_win_set_buf(panel.win, panel.buf)
            vim.wo[panel.win].wrap = true
            vim.wo[panel.win].number = false
            vim.wo[panel.win].relativenumber = false
            vim.wo[panel.win].signcolumn = "no"
        end

        vim.keymap.set("n", "q", panel.close, { buffer = panel.buf, desc = "Close panel", nowait = true })
        vim.keymap.set("n", "<Esc>", panel.close, { buffer = panel.buf, desc = "Close panel", nowait = true })
        vim.keymap.set("n", "r", panel.refresh, { buffer = panel.buf, desc = "Refresh panel", nowait = true })
        for key, fn in pairs(panel.keymaps) do
            vim.keymap.set("n", key, fn, { buffer = panel.buf, desc = "Panel action", nowait = true })
        end
        panel.refresh()
    end

    function panel.toggle()
        if panel.win and vim.api.nvim_win_is_valid(panel.win) then
            panel.close()
        else
            panel.open()
        end
    end

    return panel
end

function M.subscribe(group_name, patterns, handler)
    local group = vim.api.nvim_create_augroup(group_name, { clear = true })
    for _, pattern in ipairs(patterns) do
        vim.api.nvim_create_autocmd("User", {
            group = group,
            pattern = pattern,
            callback = handler,
        })
    end
end

return M
