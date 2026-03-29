local rpc = require("poor-cli.rpc")
local M = {}

function M.get_session_cost(params, callback) return rpc.request("poor-cli/getSessionCost", params or {}, callback) end
function M.get_economy_savings(params, callback) return rpc.request("poor-cli/getEconomySavings", params or {}, callback) end
function M.set_economy_preset(params, callback) return rpc.request("poor-cli/setEconomyPreset", params or {}, callback) end

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
    create_command("PoorCliCost", function()
        M.get_session_cost({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR); return end
            local r = result or {}
            local lines = {
                "# session cost", "",
                "Input tokens: " .. tostring(r.inputTokens or 0),
                "Output tokens: " .. tostring(r.outputTokens or 0),
                "Total tokens: " .. tostring(r.totalTokens or 0),
                "Estimated cost: $" .. tostring(r.estimatedCost or r.cost or 0),
                "Requests: " .. tostring(r.requestCount or 0),
            }
            open_scratch("[poor-cli cost]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { desc = "Show session cost" })
    create_command("PoorCliSavings", function()
        M.get_economy_savings({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR); return end
            local r = result or {}
            local lines = {
                "# economy savings", "",
                "Preset: " .. tostring(r.preset or "none"),
                "Tokens saved: " .. tostring(r.tokensSaved or 0),
                "Cost saved: $" .. tostring(r.costSaved or 0),
                "Cache hits: " .. tostring(r.cacheHits or 0),
            }
            open_scratch("[poor-cli savings]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { desc = "Show economy savings" })
    create_command("PoorCliEconomyPreset", function(opts)
        M.set_economy_preset({ preset = opts.args }, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] economy preset set: " .. opts.args, vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Set economy preset" })
end

return M
