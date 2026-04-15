local M = {
    _checked = false,
    _snacks = nil,
    _setup = false,
}

local function cfg()
    local ok, config = pcall(require, "poor-cli.config")
    if not ok or type(config.get) ~= "function" then return {} end
    local notifications = config.get("notifications")
    return type(notifications) == "table" and notifications or {}
end

local function group_name()
    local notifications = cfg()
    return notifications.group or notifications.group_name or notifications.groupName or "poor-cli"
end

function M.detect(force)
    if M._checked and not force then return M._snacks end
    M._checked = true
    local ok, snacks = pcall(require, "snacks")
    if ok and type(snacks) == "table" then
        M._snacks = snacks
        return snacks
    end
    M._snacks = nil
    return nil
end

local function route_snacks(snacks, msg, level, opts)
    if type(snacks.notify) == "function" then
        return pcall(snacks.notify, msg, level, opts)
    end
    if type(snacks.notifier) == "table" and type(snacks.notifier.notify) == "function" then
        return pcall(snacks.notifier.notify, msg, level, opts)
    end
    local global = rawget(_G, "Snacks")
    if type(global) == "table" then
        if type(global.notify) == "function" then
            return pcall(global.notify, msg, level, opts)
        end
        if type(global.notifier) == "table" and type(global.notifier.notify) == "function" then
            return pcall(global.notifier.notify, msg, level, opts)
        end
    end
    return false
end

-- collapse multi-line text into a single ·-separated line — used only as
-- a LAST RESORT when nothing better is available.
local function flatten(msg)
    local s = tostring(msg or "")
    if not s:find("\n", 1, true) then return s end
    local parts = {}
    for line in s:gmatch("([^\n]+)") do
        line = line:gsub("^%s+", ""):gsub("%s+$", "")
        if line ~= "" then parts[#parts + 1] = line end
    end
    return table.concat(parts, " · ")
end

-- pick the first non-empty line as a terse headline that fits on one row
-- without wrapping even on narrow terminals.
local function headline(msg)
    local s = tostring(msg or "")
    for line in s:gmatch("([^\n]+)") do
        line = line:gsub("^%s+", ""):gsub("%s+$", "")
        if line ~= "" then return line end
    end
    return s
end

-- write full multi-line text into :messages history via nvim_echo so the
-- user can recall with `:messages` after dismissing the short notification.
local function echo_to_history(msg, level)
    local hl = "Normal"
    if level == vim.log.levels.ERROR then hl = "ErrorMsg"
    elseif level == vim.log.levels.WARN then hl = "WarningMsg"
    elseif level == vim.log.levels.INFO then hl = "MoreMsg"
    end
    local chunks = {}
    for line in tostring(msg or ""):gmatch("([^\n]*)\n?") do
        if line ~= "" then
            chunks[#chunks + 1] = { line .. "\n", hl }
        end
    end
    if #chunks > 0 then
        -- ok=false on older neovim; swallow errors
        pcall(vim.api.nvim_echo, chunks, true, {})
    end
end

function M.notify(msg, level, opts)
    level = level or vim.log.levels.INFO
    opts = opts or {}
    local notifications = cfg()
    local snacks = notifications.snacks == false and nil or M.detect(false)
    local has_nvim_notify = pcall(require, "notify")

    -- best path: snacks or nvim-notify render multi-line natively
    if snacks then
        local snack_opts = vim.tbl_extend("keep", vim.deepcopy(opts), { group = group_name() })
        local ok, result = route_snacks(snacks, msg, level, snack_opts)
        if ok then return result end
    end
    if has_nvim_notify then
        return vim.notify(msg, level, opts)
    end

    -- plugin-less fallback: show the first line only (avoids any wrap →
    -- Press-ENTER wall on narrow terminals). Full text goes to :messages
    -- so the user can recall it; add a breadcrumb suffix when we truncated.
    local tag = "[poor-cli] "
    local one = headline(msg)
    local full = tostring(msg or "")
    local multiline = full:find("\n", 1, true) ~= nil
    if multiline then
        echo_to_history(full, level)
        one = one .. "  (run :messages for details)"
    end
    return vim.notify(tag .. one, level, opts)
end

M._flatten = flatten  -- test hook
M._headline = headline  -- test hook

-- Nudge the user once per session if neither nvim-notify nor snacks is
-- installed. ERROR/WARN notifications still work via the fallback path,
-- but multi-line toasts render much better with either plugin.
local function warn_missing_notify_plugin()
    if M._dep_checked then return end
    M._dep_checked = true
    local has_snacks = pcall(require, "snacks")
    local has_notify = pcall(require, "notify")
    if has_snacks or has_notify then return end
    local cfg_tbl = cfg()
    if cfg_tbl.suppress_notify_dep_warning == true then return end
    vim.schedule(function()
        vim.notify(
            "[poor-cli] no notification plugin detected. Install rcarriga/nvim-notify or folke/snacks.nvim for multi-line toasts. "
            .. "Suppress with: setup({ notifications = { suppress_notify_dep_warning = true } })",
            vim.log.levels.WARN
        )
    end)
end

function M.has_notify_plugin()
    return (pcall(require, "snacks") == true) or (pcall(require, "notify") == true)
end

function M.setup()
    if M._setup then return end
    M._setup = true
    M.detect(true)
    local group = vim.api.nvim_create_augroup("PoorCLINotify", { clear = true })
    vim.api.nvim_create_autocmd("VimEnter", {
        group = group,
        callback = function()
            M.detect(true)
            warn_missing_notify_plugin()
            local ok, dashboard = pcall(require, "poor-cli.snacks_dashboard")
            if ok and type(dashboard.setup) == "function" then dashboard.setup() end
        end,
    })
end

function M._reset()
    M._checked = false
    M._snacks = nil
    M._setup = false
    M._dep_checked = false
end

return M
