local rpc = require("poor-cli.rpc")
local M = {}

function M.create(params, callback) return rpc.request("poor-cli/createAgent", params or {}, callback) end
function M.list(params, callback) return rpc.request("poor-cli/listAgents", params or {}, callback) end
function M.get(params, callback) return rpc.request("poor-cli/getAgent", params or {}, callback) end
function M.start(params, callback) return rpc.request("poor-cli/startAgent", params or {}, callback) end
function M.cancel(params, callback) return rpc.request("poor-cli/cancelAgent", params or {}, callback) end
function M.get_logs(params, callback) return rpc.request("poor-cli/getAgentLogs", params or {}, callback) end
function M.get_result(params, callback) return rpc.request("poor-cli/getAgentResult", params or {}, callback) end

local function notify(msg, level) require("poor-cli.notify").notify("[poor-cli] " .. msg, level) end

local function show_detail(title, value)
    local float_win = require("poor-cli.float_win")
    local lines = vim.split(vim.inspect(value), "\n", { plain = true })
    float_win.open_lines(lines, {
        filetype = "lua",
        name = title,
        title = " " .. title:gsub("^%[", ""):gsub("%]$", "") .. " ",
        width = 0.7,
        height = 0.7,
        position = "center",
    })
end

local function format_agent(a)
    return string.format("%s  [%s]  %s",
        tostring(a.id or a.agentId or "?"),
        tostring(a.status or "unknown"),
        tostring(a.name or a.title or ""))
end

function M.open_picker()
    local pickers = require("poor-cli.pickers")
    if not rpc.is_running() then notify("server not running", vim.log.levels.WARN); return end
    rpc.request("poor-cli/listAgents", {}, function(result, err)
        vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            local agents = (result or {}).agents or {}
            if #agents == 0 then notify("no agents", vim.log.levels.INFO); return end
            local items = {}
            for _, a in ipairs(agents) do
                items[#items + 1] = {
                    id = tostring(a.id or a.agentId or "?"),
                    label = format_agent(a),
                    preview = table.concat({
                        "ID: " .. tostring(a.id or a.agentId or "?"),
                        "Name: " .. tostring(a.name or a.title or ""),
                        "Status: " .. tostring(a.status or "unknown"),
                        "Created: " .. tostring(a.createdAt or "-"),
                        "",
                        "Prompt:",
                        tostring(a.prompt or ""):sub(1, 400),
                    }, "\n"),
                    data = a,
                }
            end
            pickers.pick(items, { title = "poor-cli agents", on_pick = function(a)
                local id = tostring(a.id or a.agentId or "")
                vim.ui.select({ "start", "cancel", "logs", "result" }, { prompt = "Action for agent " .. id .. ":" }, function(choice)
                    if not choice then return end
                    if choice == "logs" then
                        M.get_logs({ agentId = id }, function(r, e) vim.schedule(function()
                            if e then notify(vim.inspect(e), vim.log.levels.ERROR); return end
                            show_detail("[poor-cli agent logs " .. id .. "]", r)
                        end) end)
                    elseif choice == "result" then
                        M.get_result({ agentId = id }, function(r, e) vim.schedule(function()
                            if e then notify(vim.inspect(e), vim.log.levels.ERROR); return end
                            show_detail("[poor-cli agent result " .. id .. "]", r)
                        end) end)
                    else
                        local map = { start = "startAgent", cancel = "cancelAgent" }
                        rpc.request("poor-cli/" .. map[choice], { agentId = id }, function(_, e) vim.schedule(function()
                            if e then notify(vim.inspect(e), vim.log.levels.ERROR)
                            else notify("agent " .. choice .. " ok", vim.log.levels.INFO) end
                        end) end)
                    end
                end)
            end })
        end)
    end)
end

local function require_id(fargs, verb)
    local id = fargs[1]
    if not id or id == "" then
        notify("usage: :PoorCLIAgent " .. verb .. " <agent-id>", vim.log.levels.WARN)
        return nil
    end
    return id
end

function M.setup()
    require("poor-cli.command_spec").install("agent", {
        desc = "Manage background agents",
        verb_names = { "list", "create", "start", "cancel", "logs", "result" },
        verbs = {
            list = function() M.open_picker() end,
            create = function()
                vim.ui.input({ prompt = "Agent name: " }, function(name)
                    if not name or name == "" then return end
                    vim.ui.input({ prompt = "Agent prompt: " }, function(prompt)
                        if not prompt or prompt == "" then return end
                        M.create({ name = name, prompt = prompt }, function(_, err) vim.schedule(function()
                            if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                            else notify("agent created", vim.log.levels.INFO) end
                        end) end)
                    end)
                end)
            end,
            start = function(fargs)
                local id = require_id(fargs, "start"); if not id then return end
                M.start({ agentId = id }, function(_, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("agent started", vim.log.levels.INFO) end
                end) end)
            end,
            cancel = function(fargs)
                local id = require_id(fargs, "cancel"); if not id then return end
                M.cancel({ agentId = id }, function(_, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("agent cancelled", vim.log.levels.INFO) end
                end) end)
            end,
            logs = function(fargs)
                local id = require_id(fargs, "logs"); if not id then return end
                M.get_logs({ agentId = id }, function(result, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    show_detail("[poor-cli agent logs " .. id .. "]", result)
                end) end)
            end,
            result = function(fargs)
                local id = require_id(fargs, "result"); if not id then return end
                M.get_result({ agentId = id }, function(result, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    show_detail("[poor-cli agent result " .. id .. "]", result)
                end) end)
            end,
        },
    })
end

return M
