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

function M.setup()
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    create_command("PoorCLIAutomations", function() M.open_picker() end, { desc = "Browse automations" })
    create_command("PoorCLIAutomationsPicker", function() M.open_picker() end, { desc = "Browse automations (alias)" })
    create_command("PoorCLIAutomationCreate", function()
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
    end, { desc = "Create automation" })
    create_command("PoorCLIAutomationEnable", function(opts)
        M.set_enabled({ automationId = opts.args, enabled = true }, function(_, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
            else notify("automation enabled", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Enable automation" })
    create_command("PoorCLIAutomationDisable", function(opts)
        M.set_enabled({ automationId = opts.args, enabled = false }, function(_, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
            else notify("automation disabled", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Disable automation" })
    create_command("PoorCLIAutomationRun", function(opts)
        M.run_now({ automationId = opts.args }, function(_, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
            else notify("automation triggered", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Run automation now" })
    create_command("PoorCLIAutomationHistory", function(opts)
        M.get_history({ automationId = opts.args }, function(result, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            show_detail("[poor-cli automation history]", result)
        end) end)
    end, { nargs = 1, desc = "Show automation history" })
    create_command("PoorCLIAutomationReplay", function(opts)
        M.replay({ automationId = opts.args }, function(_, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
            else notify("automation replayed", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Replay automation" })
end

return M
