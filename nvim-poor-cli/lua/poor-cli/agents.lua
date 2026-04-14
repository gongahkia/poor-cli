local rpc = require("poor-cli.rpc")
local M = {}

function M.create(params, callback) return rpc.request("poor-cli/createAgent", params or {}, callback) end
function M.list(params, callback) return rpc.request("poor-cli/listAgents", params or {}, callback) end
function M.get(params, callback) return rpc.request("poor-cli/getAgent", params or {}, callback) end
function M.start(params, callback) return rpc.request("poor-cli/startAgent", params or {}, callback) end
function M.cancel(params, callback) return rpc.request("poor-cli/cancelAgent", params or {}, callback) end
function M.get_logs(params, callback) return rpc.request("poor-cli/getAgentLogs", params or {}, callback) end
function M.get_result(params, callback) return rpc.request("poor-cli/getAgentResult", params or {}, callback) end

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
    vim.api.nvim_buf_set_keymap(buf, "n", "q", ":close<CR>", { noremap = true, silent = true })
    return buf
end

local function format_agent(a)
    return string.format("%s  [%s]  %s", tostring(a.id or a.agentId or "?"), tostring(a.status or "unknown"), tostring(a.name or a.title or ""))
end

function M.open_picker()
    local pickers = require("poor-cli.pickers")
    if not rpc.is_running() then require("poor-cli.notify").notify("[poor-cli] server not running", vim.log.levels.WARN); return end
    rpc.request("poor-cli/listAgents", {}, function(result, err)
        vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local agents = (result or {}).agents or {}
            if #agents == 0 then require("poor-cli.notify").notify("[poor-cli] no agents", vim.log.levels.INFO); return end
            local items = {}
            for _, a in ipairs(agents) do
                items[#items + 1] = { id = tostring(a.id or a.agentId or "?"), label = format_agent(a), preview = table.concat({
                    "ID: " .. tostring(a.id or a.agentId or "?"),
                    "Name: " .. tostring(a.name or a.title or ""),
                    "Status: " .. tostring(a.status or "unknown"),
                    "Created: " .. tostring(a.createdAt or "-"),
                }, "\n"), data = a }
            end
            pickers.pick(items, { title = "poor-cli agents", on_pick = function(a)
                local id = tostring(a.id or a.agentId or "")
                vim.ui.select({ "start", "cancel", "logs", "result" }, { prompt = "Action for agent " .. id .. ":" }, function(choice)
                    if not choice then return end
                    if choice == "logs" then
                        M.get_logs({ agentId = id }, function(r, e) vim.schedule(function()
                            if e then require("poor-cli.notify").notify("[poor-cli] " .. vim.inspect(e), vim.log.levels.ERROR); return end
                            open_scratch("[poor-cli agent logs " .. id .. "]", vim.inspect(r), "lua")
                        end) end)
                    elseif choice == "result" then
                        M.get_result({ agentId = id }, function(r, e) vim.schedule(function()
                            if e then require("poor-cli.notify").notify("[poor-cli] " .. vim.inspect(e), vim.log.levels.ERROR); return end
                            open_scratch("[poor-cli agent result " .. id .. "]", vim.inspect(r), "lua")
                        end) end)
                    else
                        local map = { start = "startAgent", cancel = "cancelAgent" }
                        rpc.request("poor-cli/" .. map[choice], { agentId = id }, function(_, e) vim.schedule(function()
                            if e then require("poor-cli.notify").notify("[poor-cli] " .. vim.inspect(e), vim.log.levels.ERROR)
                            else require("poor-cli.notify").notify("[poor-cli] agent " .. choice .. " ok", vim.log.levels.INFO) end
                        end) end)
                    end
                end)
            end })
        end)
    end)
end

function M.setup()
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    create_command("PoorCLIAgents", function()
        M.list({}, function(result, err) vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local agents = (result or {}).agents or {}
            local lines = { "# agents", "" }
            for _, a in ipairs(agents) do table.insert(lines, format_agent(a)) end
            if #agents == 0 then table.insert(lines, "no agents found") end
            open_scratch("[poor-cli agents]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { desc = "List agents" })
    create_command("PoorCLIAgentCreate", function()
        vim.ui.input({ prompt = "Agent name: " }, function(name)
            if not name or name == "" then return end
            vim.ui.input({ prompt = "Agent prompt: " }, function(prompt)
                if not prompt or prompt == "" then return end
                M.create({ name = name, prompt = prompt }, function(_, err) vim.schedule(function()
                    if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
                    else require("poor-cli.notify").notify("[poor-cli] agent created", vim.log.levels.INFO) end
                end) end)
            end)
        end)
    end, { desc = "Create agent" })
    create_command("PoorCLIAgentStart", function(opts)
        M.start({ agentId = opts.args }, function(_, err) vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
            else require("poor-cli.notify").notify("[poor-cli] agent started", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Start agent" })
    create_command("PoorCLIAgentCancel", function(opts)
        M.cancel({ agentId = opts.args }, function(_, err) vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
            else require("poor-cli.notify").notify("[poor-cli] agent cancelled", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Cancel agent" })
    create_command("PoorCLIAgentLogs", function(opts)
        M.get_logs({ agentId = opts.args }, function(result, err) vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            open_scratch("[poor-cli agent logs]", vim.inspect(result), "lua")
        end) end)
    end, { nargs = 1, desc = "Show agent logs" })
    create_command("PoorCLIAgentResult", function(opts)
        M.get_result({ agentId = opts.args }, function(result, err) vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            open_scratch("[poor-cli agent result]", vim.inspect(result), "lua")
        end) end)
    end, { nargs = 1, desc = "Show agent result" })
    create_command("PoorCLIAgentsPicker", function() M.open_picker() end, { desc = "Browse agents" })
end

return M
