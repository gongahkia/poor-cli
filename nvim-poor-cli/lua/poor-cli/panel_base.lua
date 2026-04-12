-- poor-cli/panel_base.lua
-- Shared primitives for right-split info panels (tasks, agents, history, etc.)

local M = {}

function M.new_panel(opts)
    local panel = {
        buf = nil,
        win = nil,
        name = opts.name or "[poor-cli panel]",
        width = opts.width or 60,
        filetype = opts.filetype or "markdown",
        render = opts.render or function() return {} end,
        on_refresh = opts.on_refresh,
        keymaps = opts.keymaps or {},
        events = opts.events or {},
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
        vim.cmd("botright " .. panel.width .. "vsplit")
        panel.win = vim.api.nvim_get_current_win()
        vim.api.nvim_win_set_buf(panel.win, panel.buf)
        vim.wo[panel.win].wrap = true
        vim.wo[panel.win].number = false
        vim.wo[panel.win].relativenumber = false
        vim.wo[panel.win].signcolumn = "no"

        vim.keymap.set("n", "q", panel.close, { buffer = panel.buf, desc = "Close panel", nowait = true })
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
