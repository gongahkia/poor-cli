local M = {
    _checked = false,
    _dap = nil,
    _setup = false,
    _attached = {},
}

local function cfg()
    local ok, config = pcall(require, "poor-cli.config")
    if not ok or type(config.get) ~= "function" then return {} end
    local dap = config.get("dap")
    return type(dap) == "table" and dap or {}
end

local function notify(msg, level)
    local ok, notifier = pcall(require, "poor-cli.notify")
    if ok and type(notifier.notify) == "function" then
        notifier.notify(msg, level)
    else
        vim.notify(msg, level)
    end
end

local function keymaps_enabled()
    return cfg().keymaps_enabled ~= false
end

function M.detect(force)
    if M._checked and not force then return M._dap end
    M._checked = true
    -- nvim-dap is a hard dep (see init.lua::setup); the require won't fail.
    M._dap = require("dap")
    return M._dap
end

function M.target_under_cursor()
    local ok, diagnostics = pcall(require, "poor-cli.diagnostics")
    if not ok then return nil end
    local bufnr = vim.api.nvim_get_current_buf()
    return diagnostics.diagnostic_reference_under_cursor(bufnr) or diagnostics.reference_under_cursor(bufnr)
end

local function focus_target(ref)
    if type(ref) ~= "table" or not ref.path or ref.path == "" then
        return false, "no file:line reference under cursor"
    end
    local path = vim.fn.fnamemodify(ref.path, ":p")
    if vim.fn.filereadable(path) ~= 1 then
        return false, "file is not readable: " .. path
    end
    local bufnr = vim.fn.bufnr(path)
    local wins = bufnr ~= -1 and vim.fn.win_findbuf(bufnr) or {}
    if wins[1] and vim.api.nvim_win_is_valid(wins[1]) then
        vim.api.nvim_set_current_win(wins[1])
    else
        local ok, err = pcall(vim.cmd, "edit " .. vim.fn.fnameescape(path))
        if not ok then return false, tostring(err) end
    end
    local target_line = math.max((tonumber(ref.lnum) or 0) + 1, 1)
    local max_line = math.max(vim.api.nvim_buf_line_count(0), 1)
    pcall(vim.api.nvim_win_set_cursor, 0, { math.min(target_line, max_line), 0 })
    return true
end

function M.set_breakpoint()
    local dap = M.detect(false)
    if not dap or type(dap.toggle_breakpoint) ~= "function" then
        return false, "dap_absent"
    end
    local ok, err = focus_target(M.target_under_cursor())
    if not ok then
        notify("[poor-cli] dap breakpoint: " .. err, vim.log.levels.INFO)
        return false, err
    end
    local toggled, toggle_err = pcall(dap.toggle_breakpoint)
    if not toggled then
        notify("[poor-cli] dap breakpoint failed: " .. tostring(toggle_err), vim.log.levels.WARN)
        return false, tostring(toggle_err)
    end
    return true
end

function M.run()
    local dap = M.detect(false)
    if not dap or type(dap.continue) ~= "function" then
        return false, "dap_absent"
    end
    local ok, err = M.set_breakpoint()
    if not ok then return false, err end
    local continued, continue_err = pcall(dap.continue)
    if not continued then
        notify("[poor-cli] dap run failed: " .. tostring(continue_err), vim.log.levels.WARN)
        return false, tostring(continue_err)
    end
    return true
end

function M.attach(bufnr)
    bufnr = bufnr or vim.api.nvim_get_current_buf()
    if not keymaps_enabled() or not vim.api.nvim_buf_is_valid(bufnr) then return false end
    if not M.detect(false) then return false end
    local dap_cfg = cfg()
    vim.keymap.set("n", dap_cfg.breakpoint_key or "<leader>pb", M.set_breakpoint, {
        buffer = bufnr,
        nowait = true,
        silent = true,
        desc = "poor-cli DAP breakpoint at reference",
    })
    vim.keymap.set("n", dap_cfg.run_key or "<leader>pB", M.run, {
        buffer = bufnr,
        nowait = true,
        silent = true,
        desc = "poor-cli DAP run at reference",
    })
    M._attached[bufnr] = true
    return true
end

function M.setup()
    if M._setup then return M._dap ~= nil end
    if not keymaps_enabled() then return false end
    local dap = M.detect(false)
    if not dap then return false end
    M._setup = true
    return true
end

function M._reset()
    M._checked = false
    M._dap = nil
    M._setup = false
    M._attached = {}
end

return M
