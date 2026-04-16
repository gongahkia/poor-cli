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

function M.setup()
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    create_command("PoorCLITrustStatus", function()
        M.get_status({}, function(result, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            local t = result or {}
            local lines = {
                "# trust status", "",
                "Trusted: " .. tostring(t.trusted or false),
                "Repo: " .. tostring(t.repo or t.repoPath or ""),
                "Sandbox: " .. tostring(t.sandboxPreset or ""),
                "Checkpointing: " .. tostring(t.checkpointing or false),
            }
            show_lines("[poor-cli trust status]", lines, "markdown")
        end) end)
    end, { desc = "Show trust status" })
    create_command("PoorCLITrustRepo", function()
        M.trust_repo({}, function(_, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
            else notify("repo trusted", vim.log.levels.INFO) end
        end) end)
    end, { desc = "Trust current repo" })
    create_command("PoorCLIUntrustRepo", function()
        M.untrust_repo({}, function(_, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
            else notify("repo untrusted", vim.log.levels.INFO) end
        end) end)
    end, { desc = "Untrust current repo" })
    create_command("PoorCLIProfiles", function()
        local pickers = require("poor-cli.pickers")
        M.list_profiles({}, function(result, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            local profiles = (result or {}).profiles or {}
            if #profiles == 0 then notify("no profiles found", vim.log.levels.INFO); return end
            local items = {}
            for _, p in ipairs(profiles) do
                items[#items + 1] = {
                    id = tostring(p.name or "?"),
                    label = string.format("%s: %s", tostring(p.name or "?"), tostring(p.description or "")),
                    preview = vim.inspect(p),
                    data = p,
                }
            end
            pickers.pick(items, { title = "poor-cli trust profiles", on_pick = function(p)
                M.apply_profile({ name = p.name }, function(_, e) vim.schedule(function()
                    if e then notify(rpc.format_error(e), vim.log.levels.ERROR)
                    else notify("profile applied: " .. p.name, vim.log.levels.INFO) end
                end) end)
            end })
        end) end)
    end, { desc = "List trust profiles" })
    create_command("PoorCLIProfileApply", function(opts)
        M.apply_profile({ name = opts.args }, function(_, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
            else notify("profile applied: " .. opts.args, vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Apply trust profile" })
end

return M
