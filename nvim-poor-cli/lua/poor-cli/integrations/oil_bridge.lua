-- poor-cli/integrations/oil_bridge.lua
-- Phase-B bridge. Backend fs.browse tool opens oil's file explorer for a
-- given path when oil is available; the backend still returns a listing
-- in either case (the bridge is a UX nicety, not a data source).

local M = {}

function M.open_path(params)
    local ok, oil = pcall(require, "oil")
    if not ok or not params or type(params.path) ~= "string" then return end
    pcall(oil.open, params.path)
end

function M.setup()
    local rpc = require("poor-cli.rpc")
    rpc.register_notification_handler("integration.oil.openPath", M.open_path)
end

return M
