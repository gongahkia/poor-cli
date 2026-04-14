local M = {
    mirrors = {},
    timers = {},
    poll_interval_ms = 2000,
    _setup = false,
    _overseer = nil,
}

local function task_id(task)
    if type(task) ~= "table" then return "" end
    return tostring(task.taskId or task.task_id or task.id or "")
end

local function task_title(task, id)
    local title = tostring(task.title or task.name or task.prompt or id)
    if title == "" then title = id end
    return "poor-cli: " .. title
end

local function source_status(task, data)
    local status = data and data.status or nil
    if status == nil and type(task) == "table" then status = task.status end
    return tostring(status or "")
end

local function overseer_status(status)
    if status == "completed" or status == "success" or status == "succeeded" then return "SUCCESS" end
    if status == "failed" then return "FAILURE" end
    if status == "cancelled" or status == "canceled" then return "CANCELED" end
    if status == "running" then return "RUNNING" end
    return "PENDING"
end

local function append_lines(buf, chunk)
    if not buf or not vim.api.nvim_buf_is_valid(buf) then return false end
    local lines = vim.split(tostring(chunk or ""), "\n", { plain = true })
    if lines[#lines] == "" then table.remove(lines, #lines) end
    if #lines == 0 then return false end
    local modifiable = vim.bo[buf].modifiable
    vim.bo[buf].modifiable = true
    vim.api.nvim_buf_set_lines(buf, -1, -1, false, lines)
    vim.bo[buf].modifiable = modifiable
    vim.bo[buf].modified = false
    return true
end

local function append_output(entry, chunk)
    if not entry or chunk == nil or chunk == "" then return false end
    local task = entry.task
    local strategy = task and task.strategy
    if strategy and type(strategy.send_output) == "function" then
        local ok = pcall(strategy.send_output, strategy, tostring(chunk))
        if ok then return true end
    end
    local ok, buf = pcall(function() return task:get_bufnr() end)
    if ok then return append_lines(buf, chunk) end
    return false
end

local function set_direct_status(task, status)
    if type(task.set_status) == "function" then
        local ok = pcall(task.set_status, task, status)
        if ok then return true end
    end
    if type(task.finalize) == "function" and status ~= "RUNNING" and status ~= "PENDING" then
        local ok = pcall(task.finalize, task, status)
        if ok then return true end
    end
    task.status = status
    if type(task.dispatch) == "function" then
        pcall(task.dispatch, task, "on_status", status)
        if status ~= "RUNNING" and status ~= "PENDING" then pcall(task.dispatch, task, "on_complete", status, task.result) end
    end
    return true
end

local function start_task(task)
    if type(task.start) ~= "function" then return false end
    if type(task.is_running) == "function" and task:is_running() then return true end
    return pcall(task.start, task)
end

local function finish_task(entry, target)
    if entry.finished then return end
    entry.suppress_cancel = true
    local task = entry.task
    local strategy = task and task.strategy
    if target == "CANCELED" and type(task.stop) == "function" then
        pcall(task.stop, task)
    elseif strategy and type(strategy.send_exit) == "function" then
        pcall(strategy.send_exit, strategy, target == "SUCCESS" and 0 or 1)
    else
        set_direct_status(task, target)
    end
    entry.finished = true
    entry.suppress_cancel = false
end

local function stop_timer(id)
    local timer = M.timers[id]
    if not timer then return end
    M.timers[id] = nil
    pcall(timer.stop, timer)
    pcall(timer.close, timer)
end

local function cancel_source_task(id)
    local entry = M.mirrors[id]
    if entry and entry.cancelling then return end
    if entry then entry.cancelling = true end
    local ok, tasks = pcall(require, "poor-cli.tasks")
    if not ok or type(tasks.cancel) ~= "function" then
        if entry then entry.cancelling = false end
        return
    end
    tasks.cancel({ taskId = id }, function()
        if M.mirrors[id] then M.mirrors[id].cancelling = false end
    end)
end

local function subscribe_cancel(id, task, entry)
    if type(task.subscribe) ~= "function" then return end
    pcall(task.subscribe, task, "on_status", function(_, status)
        if status == "CANCELED" and not entry.suppress_cancel then cancel_source_task(id) end
    end)
end

local function poll_task(id)
    local entry = M.mirrors[id]
    if not entry or entry.finished then stop_timer(id); return end
    local ok, tasks = pcall(require, "poor-cli.tasks")
    if not ok or type(tasks.get) ~= "function" then return end
    tasks.get({ taskId = id }, function(result, err)
        if err then return end
        vim.schedule(function()
            local task = type(result) == "table" and (result.task or result) or nil
            if task then M.handle_progress({ task = task, task_id = id, status = task.status }) end
        end)
    end)
end

local function start_poll(id)
    if M.poll_interval_ms <= 0 or M.timers[id] then return end
    local uv = vim.uv or vim.loop
    if not uv then return end
    local timer = uv.new_timer()
    if not timer then return end
    M.timers[id] = timer
    timer:start(M.poll_interval_ms, M.poll_interval_ms, vim.schedule_wrap(function() poll_task(id) end))
end

function M.create_mirror(task)
    local id = task_id(task)
    if id == "" then return nil end
    if M.mirrors[id] then return M.mirrors[id] end
    if not M._overseer or type(M._overseer.new_task) ~= "function" then return nil end
    local ok, mirror = pcall(M._overseer.new_task, {
        name = task_title(task, id),
        cwd = task.repoRoot or task.repo_root or task.worktreePath or task.worktree_path or vim.fn.getcwd(),
        strategy = { "test" },
        components = { "default" },
        metadata = { poor_cli_task_id = id, poor_cli_mirror = true },
    })
    if not ok or not mirror then return nil end
    local entry = { task = mirror, source = task, finished = false, suppress_cancel = false, cancelling = false }
    M.mirrors[id] = entry
    subscribe_cancel(id, mirror, entry)
    start_task(mirror)
    start_poll(id)
    return entry
end

function M.update_status(id, status)
    local entry = M.mirrors[id]
    if not entry then return false end
    local target = overseer_status(status)
    if target == "RUNNING" then
        start_task(entry.task)
    elseif target ~= "PENDING" then
        finish_task(entry, target)
        stop_timer(id)
    else
        set_direct_status(entry.task, target)
    end
    return true
end

function M.handle_started(data)
    data = data or {}
    local task = data.task or data
    local id = task_id(task)
    if id == "" then id = tostring(data.task_id or data.taskId or "") end
    if id == "" then return false end
    task.taskId = task.taskId or id
    local entry = M.create_mirror(task)
    local status = source_status(task, data)
    if status == "" then status = "running" end
    if entry then M.update_status(id, status) end
    return entry ~= nil
end

function M.handle_progress(data)
    data = data or {}
    local task = data.task or data
    local id = tostring(data.task_id or data.taskId or task_id(task))
    if id == "" then return false end
    local entry = M.mirrors[id]
    if not entry and source_status(task, data) == "running" then entry = M.create_mirror(task) end
    if not entry then return false end
    entry.source = task
    return M.update_status(id, source_status(task, data))
end

function M.handle_finished(data)
    return M.handle_progress(data)
end

local function chunk_ids(data)
    local ids = {}
    local task = tostring(data.task_id or data.taskId or "")
    if task ~= "" then table.insert(ids, task) end
    local req = tostring(data.request_id or data.requestId or "")
    if req:sub(1, 5) == "task-" then table.insert(ids, req:sub(6)) end
    if req ~= "" then table.insert(ids, req) end
    return ids
end

function M.handle_tool_chunk(data)
    data = data or {}
    local chunk = data.chunk
    for _, id in ipairs(chunk_ids(data)) do
        local entry = M.mirrors[id]
        if entry then return append_output(entry, chunk) end
    end
    return false
end

function M.setup()
    if M._setup then return true end
    local ok, overseer = pcall(require, "overseer")
    if not ok then return false end
    M._overseer = overseer
    M._setup = true
    local group = vim.api.nvim_create_augroup("PoorCLIOverseer", { clear = true })
    vim.api.nvim_create_autocmd("User", { group = group, pattern = "PoorCLITaskStarted", callback = function(ev) M.handle_started(ev.data or {}) end })
    vim.api.nvim_create_autocmd("User", { group = group, pattern = "PoorCLITaskProgress", callback = function(ev) M.handle_progress(ev.data or {}) end })
    vim.api.nvim_create_autocmd("User", { group = group, pattern = "PoorCLITaskFinished", callback = function(ev) M.handle_finished(ev.data or {}) end })
    vim.api.nvim_create_autocmd("User", { group = group, pattern = "PoorCLIToolChunk", callback = function(ev) M.handle_tool_chunk(ev.data or {}) end })
    return true
end

function M._reset()
    for id, _ in pairs(M.timers) do stop_timer(id) end
    M.mirrors = {}
    M._setup = false
    M._overseer = nil
    pcall(vim.api.nvim_del_augroup_by_name, "PoorCLIOverseer")
end

return M
