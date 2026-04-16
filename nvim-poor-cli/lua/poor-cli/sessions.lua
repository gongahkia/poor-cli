local rpc = require("poor-cli.rpc")
local M = {}

function M.create(params, callback) return rpc.request("poor-cli/createSession", params or {}, callback) end
function M.list(params, callback) return rpc.request("poor-cli/listMuxSessions", params or {}, callback) end
function M.switch(params, callback) return rpc.request("poor-cli/switchSession", params or {}, callback) end
function M.fork(params, callback) return rpc.request("poor-cli/forkSession", params or {}, callback) end
function M.destroy(params, callback) return rpc.request("poor-cli/destroySession", params or {}, callback) end
function M.rename(params, callback) return rpc.request("poor-cli/renameSession", params or {}, callback) end
function M.save(params, callback) return rpc.request("poor-cli/saveSession", params or {}, callback) end
function M.restore(params, callback) return rpc.request("poor-cli/restoreSession", params or {}, callback) end

local function notify(msg, level) require("poor-cli.notify").notify("[poor-cli] " .. msg, level) end

local function format_session(s)
    local active = s.active and " *" or ""
    return string.format("%s  %s%s", tostring(s.id or s.sessionId or "?"), tostring(s.name or "unnamed"), active)
end

function M.open_picker()
    local pickers = require("poor-cli.pickers")
    if not rpc.is_running() then notify("server not running", vim.log.levels.WARN); return end
    rpc.request("poor-cli/listMuxSessions", {}, function(result, err)
        vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            local sessions = (result or {}).sessions or {}
            if #sessions == 0 then notify("no sessions", vim.log.levels.INFO); return end
            local items = {}
            for _, s in ipairs(sessions) do
                items[#items + 1] = {
                    id = tostring(s.id or s.sessionId or "?"),
                    label = format_session(s),
                    preview = table.concat({
                        "ID: " .. tostring(s.id or s.sessionId or "?"),
                        "Name: " .. tostring(s.name or "unnamed"),
                        "Active: " .. tostring(s.active or false),
                        "Created: " .. tostring(s.createdAt or "-"),
                    }, "\n"),
                    data = s,
                }
            end
            pickers.pick(items, { title = "poor-cli sessions", on_pick = function(s)
                local id = tostring(s.id or s.sessionId or "")
                vim.ui.select({ "switch", "fork", "destroy" }, { prompt = "Action for session " .. id .. ":" }, function(choice)
                    if not choice then return end
                    local method_map = { switch = "switchSession", fork = "forkSession", destroy = "destroySession" }
                    rpc.request("poor-cli/" .. method_map[choice], { sessionId = id }, function(_, e) vim.schedule(function()
                        if e then notify(vim.inspect(e), vim.log.levels.ERROR)
                        else notify("session " .. id .. " " .. choice .. " ok", vim.log.levels.INFO) end
                    end) end)
                end)
            end })
        end)
    end)
end

function M.setup()
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    create_command("PoorCLISessions", function() M.open_picker() end, { desc = "Browse sessions" })
    create_command("PoorCLISessionsPicker", function() M.open_picker() end, { desc = "Browse sessions (alias)" })
    create_command("PoorCLISessionCreate", function()
        vim.ui.input({ prompt = "Session name: " }, function(name)
            if not name or name == "" then return end
            M.create({ name = name }, function(_, err) vim.schedule(function()
                if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                else notify("session created", vim.log.levels.INFO) end
            end) end)
        end)
    end, { desc = "Create session" })
    create_command("PoorCLISessionSwitch", function(opts)
        M.switch({ sessionId = opts.args }, function(_, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
            else notify("session switched", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Switch session" })
    create_command("PoorCLISessionFork", function(opts)
        M.fork({ sessionId = opts.args }, function(_, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
            else notify("session forked", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Fork session" })
    create_command("PoorCLISessionDestroy", function(opts)
        M.destroy({ sessionId = opts.args }, function(_, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
            else notify("session destroyed", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Destroy session" })
    create_command("PoorCLISessionRename", function(opts)
        local args = vim.split(opts.args, " ", { trimempty = true })
        if #args < 2 then notify("usage: :PoorCLISessionRename <id> <name>", vim.log.levels.WARN); return end
        M.rename({ sessionId = args[1], name = table.concat(args, " ", 2) }, function(_, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
            else notify("session renamed", vim.log.levels.INFO) end
        end) end)
    end, { nargs = "+", desc = "Rename session" })
    create_command("PoorCLISessionSave", function()
        M.save({}, function(_, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
            else notify("session saved", vim.log.levels.INFO) end
        end) end)
    end, { desc = "Save session" })
    create_command("PoorCLISessionRestore", function()
        M.restore({}, function(_, err) vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
            else notify("session restored", vim.log.levels.INFO) end
        end) end)
    end, { desc = "Restore session" })
end

return M
