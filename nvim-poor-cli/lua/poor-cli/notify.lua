-- poor-cli/notify.lua
-- Thin shim over snacks.notify. snacks.nvim is a hard dependency (enforced in
-- init.lua::setup), so we don't carry a fallback cascade here.

local M = { _setup = false }

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

local function snacks_notify()
    local s = require("snacks")
    if type(s.notify) == "function" then return s.notify end
    if type(s.notifier) == "table" and type(s.notifier.notify) == "function" then
        return s.notifier.notify
    end
    local global = rawget(_G, "Snacks")
    if type(global) == "table" then
        if type(global.notify) == "function" then return global.notify end
        if type(global.notifier) == "table" and type(global.notifier.notify) == "function" then
            return global.notifier.notify
        end
    end
    return nil
end

function M.notify(msg, level, opts)
    level = level or vim.log.levels.INFO
    opts = vim.tbl_extend("keep", vim.deepcopy(opts or {}), { group = group_name() })
    local notify_fn = snacks_notify()
    if notify_fn then return notify_fn(msg, level, opts) end
    -- snacks is a hard dep but its notify entry can momentarily be absent
    -- (e.g. during lazy-load before VimEnter). Fall through to vim.notify
    -- rather than crashing the caller.
    return vim.notify(tostring(msg), level, opts)
end

function M.has_notify_plugin()
    return snacks_notify() ~= nil
end

function M.detect()
    return (pcall(require, "snacks") and require("snacks")) or nil
end

function M.setup()
    if M._setup then return end
    M._setup = true
end

function M._reset()
    M._setup = false
end

return M
