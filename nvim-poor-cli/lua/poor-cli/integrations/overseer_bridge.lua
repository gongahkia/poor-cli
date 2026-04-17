-- poor-cli/integrations/overseer_bridge.lua
-- Phase-B bridge. Backend task.run tool invokes overseer's task templates
-- when available so the user sees the task in overseer's UI. Falls back to
-- raw subprocess on the backend side when overseer is missing.

local M = {}
local _pending_results = {} -- token → task ref for request-response pairing

function M.run_template(params)
    local ok, overseer = pcall(require, "overseer")
    if not ok or not params or type(params.name) ~= "string" then return end
    local task_args = params.args or {}
    pcall(function()
        overseer.run_template({ name = params.name, params = task_args })
    end)
end

function M.setup()
    local rpc = require("poor-cli.rpc")
    rpc.register_notification_handler("integration.overseer.runTemplate", M.run_template)
end

return M
