local rpc = require("poor-cli.rpc")
local M = {}

local terminal_statuses = { completed = true, success = true, succeeded = true, failed = true, cancelled = true, canceled = true }

local function task_payload(result)
    if type(result) ~= "table" then return nil end
    if type(result.task) == "table" then return result.task end
    return result
end

local function task_id(task)
    if type(task) ~= "table" then return "" end
    return tostring(task.taskId or task.task_id or task.id or "")
end

local function emit_task_event(task, event)
    if type(task) ~= "table" then return end
    local id = task_id(task)
    if id == "" then return end
    vim.api.nvim_exec_autocmds("User", {
        pattern = event,
        data = { task = task, task_id = id, status = tostring(task.status or ""), source = "tasks.lua" },
    })
end

local function emit_task_state(result)
    local task = task_payload(result)
    if not task then return end
    local status = tostring(task.status or "")
    if status == "running" then emit_task_event(task, "PoorCLITaskStarted") end
    emit_task_event(task, "PoorCLITaskProgress")
    if terminal_statuses[status] then emit_task_event(task, "PoorCLITaskFinished") end
end

local function task_request(method, params, callback)
    return rpc.request(method, params or {}, function(result, err)
        if not err then emit_task_state(result) end
        if callback then callback(result, err) end
    end)
end

function M.create(params, callback) return task_request("poor-cli/createTask", params, callback) end
function M.list(params, callback) return rpc.request("poor-cli/listTasks", params or {}, callback) end
function M.get(params, callback) return rpc.request("poor-cli/getTask", params or {}, callback) end
function M.start(params, callback) return task_request("poor-cli/startTask", params, callback) end
function M.approve(params, callback) return task_request("poor-cli/approveTask", params, callback) end
function M.cancel(params, callback) return task_request("poor-cli/cancelTask", params, callback) end
function M.retry(params, callback) return task_request("poor-cli/retryTask", params, callback) end
function M.replay(params, callback) return task_request("poor-cli/replayTask", params, callback) end

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

local function format_task(t)
    return string.format("%s  [%s]  %s", tostring(t.id or t.taskId or "?"), tostring(t.status or "unknown"), tostring(t.title or ""))
end

function M.open_picker()
    local pickers = require("poor-cli.pickers")
    if not rpc.is_running() then notify("server not running", vim.log.levels.WARN); return end
    rpc.request("poor-cli/listTasks", {}, function(result, err)
        vim.schedule(function()
            if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
            local tasks = (result or {}).tasks or {}
            if #tasks == 0 then notify("no tasks", vim.log.levels.INFO); return end
            local items = {}
            for _, t in ipairs(tasks) do
                items[#items + 1] = {
                    id = tostring(t.id or t.taskId or "?"),
                    label = format_task(t),
                    preview = table.concat({
                        "ID: " .. tostring(t.id or t.taskId or "?"),
                        "Title: " .. tostring(t.title or ""),
                        "Status: " .. tostring(t.status or "unknown"),
                        "Prompt: " .. tostring(t.prompt or ""),
                        "Created: " .. tostring(t.createdAt or "-"),
                    }, "\n"),
                    data = t,
                }
            end
            pickers.pick(items, { title = "poor-cli tasks", on_pick = function(t)
                local id = tostring(t.id or t.taskId or "")
                vim.ui.select({ "start", "approve", "cancel", "retry", "replay", "show" }, { prompt = "Action for task " .. id .. ":" }, function(choice)
                    if not choice then return end
                    if choice == "show" then
                        M.get({ taskId = id }, function(r, e) vim.schedule(function()
                            if e then notify(vim.inspect(e), vim.log.levels.ERROR); return end
                            show_detail("[poor-cli task " .. id .. "]", r)
                        end) end)
                    else
                        local method_map = { start = "startTask", approve = "approveTask", cancel = "cancelTask", retry = "retryTask", replay = "replayTask" }
                        rpc.request("poor-cli/" .. method_map[choice], { taskId = id }, function(_, e) vim.schedule(function()
                            if e then notify(vim.inspect(e), vim.log.levels.ERROR)
                            else notify("task " .. id .. " " .. choice .. " ok", vim.log.levels.INFO) end
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
        notify("usage: :PoorCLITask " .. verb .. " <task-id>", vim.log.levels.WARN)
        return nil
    end
    return id
end

local function action(method_name, verb, fargs, success_msg)
    local id = require_id(fargs, verb); if not id then return end
    rpc.request("poor-cli/" .. method_name, { taskId = id }, function(_, err) vim.schedule(function()
        if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
        else notify(success_msg, vim.log.levels.INFO) end
    end) end)
end

function M.setup()
    -- v6.2: absorbed into :PoorCLIAgent as `task`, `task-create`, etc.
    local spec = require("poor-cli.command_spec")
    spec.extend("agent", {
        verb_prefix = "task-",
        verbs = {
            create = function()
                vim.ui.input({ prompt = "Task title: " }, function(title)
                    if not title or title == "" then return end
                    vim.ui.input({ prompt = "Task prompt: " }, function(prompt)
                        if not prompt or prompt == "" then return end
                        M.create({ title = title, prompt = prompt }, function(_, err) vim.schedule(function()
                            if err then notify(rpc.format_error(err), vim.log.levels.ERROR)
                            else notify("task created", vim.log.levels.INFO) end
                        end) end)
                    end)
                end)
            end,
            start   = function(fargs) action("startTask",   "start",   fargs, "task started")   end,
            approve = function(fargs) action("approveTask", "approve", fargs, "task approved")  end,
            cancel  = function(fargs) action("cancelTask",  "cancel",  fargs, "task cancelled") end,
            retry   = function(fargs) action("retryTask",   "retry",   fargs, "task retried")   end,
            replay  = function(fargs) action("replayTask",  "replay",  fargs, "task replayed")  end,
            show = function(fargs)
                local id = require_id(fargs, "show"); if not id then return end
                M.get({ taskId = id }, function(result, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    show_detail("[poor-cli task " .. id .. "]", result)
                end) end)
            end,
        },
    })
    -- Bare `task` verb opens the picker.
    spec.extend("agent", {
        verbs = { task = function() M.open_picker() end },
    })
end

return M
