-- poor-cli/integrations/trouble_bridge.lua
-- Phase-B bridge. Backend diagnostics.emit tool calls push agent-emitted
-- findings into vim.diagnostic under the poor-cli namespace, which the
-- existing trouble_source.lua surfaces in :Trouble poor-cli.

local M = {}
local NS_NAME = "poor-cli-agent"
local _ns

local function ns()
    if _ns then return _ns end
    _ns = vim.api.nvim_create_namespace(NS_NAME)
    return _ns
end

local SEVERITY_MAP = {
    error = vim.diagnostic.severity.ERROR,
    warn = vim.diagnostic.severity.WARN,
    warning = vim.diagnostic.severity.WARN,
    info = vim.diagnostic.severity.INFO,
    hint = vim.diagnostic.severity.HINT,
}

-- Notification params:
--   { items = [{ file, line, col?, end_line?, end_col?, severity, message }] }
function M.emit(params)
    params = params or {}
    local items = params.items or {}
    if #items == 0 then return end
    local by_buf = {}
    for _, item in ipairs(items) do
        local file = item.file
        if type(file) == "string" and file ~= "" then
            local buf = vim.fn.bufnr(file, true)
            if buf > 0 then
                by_buf[buf] = by_buf[buf] or {}
                table.insert(by_buf[buf], {
                    lnum = math.max(0, (tonumber(item.line) or 1) - 1),
                    col = math.max(0, tonumber(item.col) or 0),
                    end_lnum = math.max(0, (tonumber(item.end_line) or item.line or 1) - 1),
                    end_col = math.max(0, tonumber(item.end_col) or item.col or 0),
                    severity = SEVERITY_MAP[(item.severity or "info"):lower()] or vim.diagnostic.severity.INFO,
                    message = tostring(item.message or ""),
                    source = "poor-cli",
                })
            end
        end
    end
    for buf, list in pairs(by_buf) do
        pcall(vim.diagnostic.set, ns(), buf, list)
    end
end

function M.clear(_)
    for _, buf in ipairs(vim.api.nvim_list_bufs()) do
        pcall(vim.diagnostic.reset, ns(), buf)
    end
end

function M.setup()
    local rpc = require("poor-cli.rpc")
    rpc.register_notification_handler("integration.trouble.emit", M.emit)
    rpc.register_notification_handler("integration.trouble.clear", M.clear)
end

return M
