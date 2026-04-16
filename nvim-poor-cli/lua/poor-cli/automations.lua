local rpc = require("poor-cli.rpc")
local M = {}

function M.create(params, callback) return rpc.request("poor-cli/createAutomation", params or {}, callback) end
function M.list(params, callback) return rpc.request("poor-cli/listAutomations", params or {}, callback) end
function M.get(params, callback) return rpc.request("poor-cli/getAutomation", params or {}, callback) end
function M.set_enabled(params, callback) return rpc.request("poor-cli/setAutomationEnabled", params or {}, callback) end
function M.run_now(params, callback) return rpc.request("poor-cli/runAutomationNow", params or {}, callback) end
function M.run_due(params, callback) return rpc.request("poor-cli/runDueAutomations", params or {}, callback) end
function M.get_history(params, callback) return rpc.request("poor-cli/getAutomationHistory", params or {}, callback) end
function M.replay(params, callback) return rpc.request("poor-cli/replayAutomation", params or {}, callback) end

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

local function format_auto(a)
    local enabled = a.enabled and "on" or "off"
    return string.format("%s  [%s]  %s  %s",
        tostring(a.id or a.automationId or "?"),
        enabled,
        tostring(a.schedule or ""),
        tostring(a.name or a.title or ""))
end

function M.open_picker()
    local pickers = require("poor-cli.pickers")
    if not rpc.is_running() then notify("server not running", vim.log.levels.WARN); return end
    rpc.request("poor-cli/listAutomations", {}, function(result, err)
        vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            local autos = (result or {}).automations or {}
            if #autos == 0 then notify("no automations", vim.log.levels.INFO); return end
            local items = {}
            for _, a in ipairs(autos) do
                items[#items + 1] = {
                    id = tostring(a.id or a.automationId or "?"),
                    label = format_auto(a),
                    preview = table.concat({
                        "ID: " .. tostring(a.id or a.automationId or "?"),
                        "Name: " .. tostring(a.name or a.title or ""),
                        "Schedule: " .. tostring(a.schedule or ""),
                        "Enabled: " .. tostring(a.enabled or false),
                        "Prompt: " .. tostring(a.prompt or ""),
                        "Created: " .. tostring(a.createdAt or "-"),
                    }, "\n"),
                    data = a,
                }
            end
            pickers.pick(items, { title = "poor-cli automations", on_pick = function(a)
                local id = tostring(a.id or a.automationId or "")
                vim.ui.select({ "enable", "disable", "run", "history", "replay" }, { prompt = "Action for " .. id .. ":" }, function(choice)
                    if not choice then return end
                    local map = {
                        enable = { "setAutomationEnabled", { automationId = id, enabled = true } },
                        disable = { "setAutomationEnabled", { automationId = id, enabled = false } },
                        run = { "runAutomationNow", { automationId = id } },
                        history = { "getAutomationHistory", { automationId = id } },
                        replay = { "replayAutomation", { automationId = id } },
                    }
                    local m = map[choice]
                    rpc.request("poor-cli/" .. m[1], m[2], function(r, e) vim.schedule(function()
                        if e then notify(vim.inspect(e), vim.log.levels.ERROR)
                        elseif choice == "history" then show_detail("[poor-cli automation history]", r)
                        else notify("automation " .. choice .. " ok", vim.log.levels.INFO) end
                    end) end)
                end)
            end })
        end)
    end)
end

local function require_id(fargs, verb)
    local id = fargs[1]
    if not id or id == "" then
        notify("usage: :PoorCLIAutomation " .. verb .. " <automation-id>", vim.log.levels.WARN)
        return nil
    end
    return id
end

function M.setup()
    require("poor-cli.command_spec").install("automation", {
        desc = "Manage scheduled automations",
        verb_names = { "list", "create", "enable", "disable", "run", "history", "replay" },
        verbs = {
            list = function() M.open_picker() end,
            create = function()
                vim.ui.input({ prompt = "Automation name: " }, function(name)
                    if not name or name == "" then return end
                    vim.ui.input({ prompt = "Schedule (cron): " }, function(schedule)
                        if not schedule or schedule == "" then return end
                        vim.ui.input({ prompt = "Prompt: " }, function(prompt)
                            if not prompt or prompt == "" then return end
                            M.create({ name = name, schedule = schedule, prompt = prompt }, function(_, err) vim.schedule(function()
                                if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                                else notify("automation created", vim.log.levels.INFO) end
                            end) end)
                        end)
                    end)
                end)
            end,
            enable = function(fargs)
                local id = require_id(fargs, "enable"); if not id then return end
                M.set_enabled({ automationId = id, enabled = true }, function(_, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("automation enabled", vim.log.levels.INFO) end
                end) end)
            end,
            disable = function(fargs)
                local id = require_id(fargs, "disable"); if not id then return end
                M.set_enabled({ automationId = id, enabled = false }, function(_, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("automation disabled", vim.log.levels.INFO) end
                end) end)
            end,
            run = function(fargs)
                local id = require_id(fargs, "run"); if not id then return end
                M.run_now({ automationId = id }, function(_, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("automation triggered", vim.log.levels.INFO) end
                end) end)
            end,
            history = function(fargs)
                local id = require_id(fargs, "history"); if not id then return end
                M.get_history({ automationId = id }, function(result, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    show_detail("[poor-cli automation history " .. id .. "]", result)
                end) end)
            end,
            replay = function(fargs)
                local id = require_id(fargs, "replay"); if not id then return end
                M.replay({ automationId = id }, function(_, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("automation replayed", vim.log.levels.INFO) end
                end) end)
            end,
        },
    })
end

return M
