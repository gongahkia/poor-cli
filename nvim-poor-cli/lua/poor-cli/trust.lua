local rpc = require("poor-cli.rpc")
local M = {}

function M.get_status(params, callback) return rpc.request("poor-cli/getTrustStatus", params or {}, callback) end
function M.trust_repo(params, callback) return rpc.request("poor-cli/trustRepo", params or {}, callback) end
function M.untrust_repo(params, callback) return rpc.request("poor-cli/untrustRepo", params or {}, callback) end
function M.list_profiles(params, callback) return rpc.request("poor-cli/listProfiles", params or {}, callback) end
function M.apply_profile(params, callback) return rpc.request("poor-cli/applyProfile", params or {}, callback) end

local function open_scratch(title, content, filetype)
    local buf = vim.api.nvim_create_buf(false, true)
    vim.bo[buf].buftype = "nofile"
    vim.bo[buf].bufhidden = "wipe"
    vim.bo[buf].swapfile = false
    vim.bo[buf].filetype = filetype or "markdown"
    vim.api.nvim_buf_set_name(buf, title)
    vim.api.nvim_buf_set_lines(buf, 0, -1, false, vim.split(content, "\n", { plain = true }))
    vim.cmd("botright split")
    vim.api.nvim_win_set_buf(0, buf)
    return buf
end

function M.setup()
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    create_command("PoorCliTrustStatus", function()
        M.get_status({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR); return end
            local t = result or {}
            local lines = {
                "# trust status", "",
                "Trusted: " .. tostring(t.trusted or false),
                "Repo: " .. tostring(t.repo or t.repoPath or ""),
                "Sandbox: " .. tostring(t.sandboxPreset or ""),
                "Checkpointing: " .. tostring(t.checkpointing or false),
            }
            open_scratch("[poor-cli trust status]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { desc = "Show trust status" })
    create_command("PoorCliTrustRepo", function()
        M.trust_repo({}, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] repo trusted", vim.log.levels.INFO) end
        end) end)
    end, { desc = "Trust current repo" })
    create_command("PoorCliUntrustRepo", function()
        M.untrust_repo({}, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] repo untrusted", vim.log.levels.INFO) end
        end) end)
    end, { desc = "Untrust current repo" })
    create_command("PoorCliProfiles", function()
        M.list_profiles({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR); return end
            local profiles = (result or {}).profiles or {}
            local lines = { "# profiles", "" }
            for _, p in ipairs(profiles) do
                table.insert(lines, string.format("%s: %s", tostring(p.name or "?"), tostring(p.description or "")))
            end
            if #profiles == 0 then table.insert(lines, "no profiles found") end
            open_scratch("[poor-cli profiles]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { desc = "List trust profiles" })
    create_command("PoorCliProfileApply", function(opts)
        M.apply_profile({ name = opts.args }, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] profile applied: " .. opts.args, vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Apply trust profile" })
end

return M
