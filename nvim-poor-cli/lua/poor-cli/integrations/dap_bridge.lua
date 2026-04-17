-- poor-cli/integrations/dap_bridge.lua
-- Phase-B bridge. Backend debug.* tool handlers drive nvim-dap via these
-- handlers (notification for set/step/continue, request for stack/eval).

local M = {}

local function dap_require()
    local ok, dap = pcall(require, "dap")
    if not ok then return nil end
    return dap
end

function M.set_breakpoint(params)
    local dap = dap_require()
    if not dap or not params or not params.file then return end
    pcall(function()
        vim.cmd("edit " .. vim.fn.fnameescape(params.file))
        pcall(vim.api.nvim_win_set_cursor, 0, { math.max(1, tonumber(params.line) or 1), 0 })
        if params.condition then
            dap.set_breakpoint(params.condition)
        else
            dap.toggle_breakpoint()
        end
    end)
end

function M.clear_breakpoint(params)
    local dap = dap_require()
    if not dap or not params or not params.file then return end
    pcall(function()
        vim.cmd("edit " .. vim.fn.fnameescape(params.file))
        pcall(vim.api.nvim_win_set_cursor, 0, { math.max(1, tonumber(params.line) or 1), 0 })
        dap.toggle_breakpoint()
    end)
end

function M.step(params)
    local dap = dap_require()
    if not dap or not params then return end
    local direction = (params.direction or "over"):lower()
    if direction == "in" then pcall(dap.step_into)
    elseif direction == "out" then pcall(dap.step_out)
    else pcall(dap.step_over) end
end

function M.continue(_)
    local dap = dap_require()
    if dap then pcall(dap.continue) end
end

function M.setup()
    local rpc = require("poor-cli.rpc")
    rpc.register_notification_handler("integration.dap.setBreakpoint", M.set_breakpoint)
    rpc.register_notification_handler("integration.dap.clearBreakpoint", M.clear_breakpoint)
    rpc.register_notification_handler("integration.dap.step", M.step)
    rpc.register_notification_handler("integration.dap.continue", M.continue)
end

return M
