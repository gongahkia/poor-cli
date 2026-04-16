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

local function require_id(fargs, verb)
    local id = fargs[1]
    if not id or id == "" then
        notify("usage: :PoorCLISession " .. verb .. " <session-id>", vim.log.levels.WARN)
        return nil
    end
    return id
end

function M.setup()
    require("poor-cli.command_spec").install("session", {
        desc = "Manage conversation sessions",
        verb_names = { "list", "create", "switch", "fork", "destroy", "rename", "save", "restore", "branches" },
        verbs = {
            list = function() M.open_picker() end,
            create = function()
                vim.ui.input({ prompt = "Session name: " }, function(name)
                    if not name or name == "" then return end
                    M.create({ name = name }, function(_, err) vim.schedule(function()
                        if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                        else notify("session created", vim.log.levels.INFO) end
                    end) end)
                end)
            end,
            switch = function(fargs)
                local id = require_id(fargs, "switch"); if not id then return end
                M.switch({ sessionId = id }, function(_, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("session switched", vim.log.levels.INFO) end
                end) end)
            end,
            fork = function(fargs)
                local id = require_id(fargs, "fork"); if not id then return end
                M.fork({ sessionId = id }, function(_, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("session forked", vim.log.levels.INFO) end
                end) end)
            end,
            destroy = function(fargs)
                local id = require_id(fargs, "destroy"); if not id then return end
                M.destroy({ sessionId = id }, function(_, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("session destroyed", vim.log.levels.INFO) end
                end) end)
            end,
            rename = function(fargs)
                if #fargs < 2 then notify("usage: :PoorCLISession rename <id> <name>", vim.log.levels.WARN); return end
                local id = fargs[1]
                local name = table.concat(fargs, " ", 2)
                M.rename({ sessionId = id, name = name }, function(_, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("session renamed", vim.log.levels.INFO) end
                end) end)
            end,
            save = function()
                M.save({}, function(_, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("session saved", vim.log.levels.INFO) end
                end) end)
            end,
            restore = function()
                M.restore({}, function(_, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                    else notify("session restored", vim.log.levels.INFO) end
                end) end)
            end,
            branches = function() require("poor-cli.branches").open() end,
        },
    })
end

return M
