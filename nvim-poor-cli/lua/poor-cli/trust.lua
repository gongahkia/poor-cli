local rpc = require("poor-cli.rpc")
local M = {}

function M.get_status(params, callback) return rpc.request("poor-cli/getTrustStatus", params or {}, callback) end
function M.trust_repo(params, callback) return rpc.request("poor-cli/trustRepo", params or {}, callback) end
function M.untrust_repo(params, callback) return rpc.request("poor-cli/untrustRepo", params or {}, callback) end
function M.list_profiles(params, callback) return rpc.request("poor-cli/listProfiles", params or {}, callback) end
function M.apply_profile(params, callback) return rpc.request("poor-cli/applyProfile", params or {}, callback) end

local function notify(msg, level) require("poor-cli.notify").notify("[poor-cli] " .. msg, level) end

local function show_lines(title, lines, filetype)
    local float_win = require("poor-cli.float_win")
    float_win.open_lines(lines, {
        filetype = filetype or "markdown",
        name = title,
        title = " " .. title:gsub("^%[", ""):gsub("%]$", "") .. " ",
        width = 0.6,
        height = 0.5,
        position = "center",
    })
end

-- setup() intentionally removed: trust verbs live on the :PoorCLITrust
-- dispatcher owned by commands.lua, and profile verbs live on :PoorCLIProfile.
-- M.get_status/M.trust_repo/M.untrust_repo/M.list_profiles/M.apply_profile
-- remain as the module API for any programmatic callers.
function M.setup() end

return M
