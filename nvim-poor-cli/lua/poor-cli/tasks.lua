local rpc = require("poor-cli.rpc")
local M = {}

function M.create(params, callback) return rpc.request("poor-cli/createTask", params or {}, callback) end
function M.list(params, callback) return rpc.request("poor-cli/listTasks", params or {}, callback) end
function M.get(params, callback) return rpc.request("poor-cli/getTask", params or {}, callback) end
function M.start(params, callback) return rpc.request("poor-cli/startTask", params or {}, callback) end
function M.approve(params, callback) return rpc.request("poor-cli/approveTask", params or {}, callback) end
function M.cancel(params, callback) return rpc.request("poor-cli/cancelTask", params or {}, callback) end
function M.retry(params, callback) return rpc.request("poor-cli/retryTask", params or {}, callback) end
function M.replay(params, callback) return rpc.request("poor-cli/replayTask", params or {}, callback) end

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

local function format_task(t)
    return string.format("%s  [%s]  %s", tostring(t.id or t.taskId or "?"), tostring(t.status or "unknown"), tostring(t.title or ""))
end

function M.open_picker()
    local has_telescope, pickers = pcall(require, "telescope.pickers")
    if not has_telescope then vim.notify("[poor-cli] telescope.nvim required", vim.log.levels.ERROR); return end
    local finders = require("telescope.finders")
    local conf = require("telescope.config").values
    local actions = require("telescope.actions")
    local action_state = require("telescope.actions.state")
    local previewers = require("telescope.previewers")
    if not rpc.is_running() then vim.notify("[poor-cli] server not running", vim.log.levels.WARN); return end
    rpc.request("poor-cli/listTasks", {}, function(result, err)
        vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR); return end
            local tasks = (result or {}).tasks or {}
            if #tasks == 0 then vim.notify("[poor-cli] no tasks", vim.log.levels.INFO); return end
            pickers.new({}, {
                prompt_title = "poor-cli tasks",
                finder = finders.new_table({
                    results = tasks,
                    entry_maker = function(t)
                        local id = tostring(t.id or t.taskId or "?")
                        return { value = t, ordinal = id .. " " .. tostring(t.title or ""), display = format_task(t) }
                    end,
                }),
                sorter = conf.generic_sorter({}),
                previewer = previewers.new_buffer_previewer({
                    title = "Task Preview",
                    define_preview = function(self, entry)
                        local t = entry.value
                        local lines = {
                            "ID: " .. tostring(t.id or t.taskId or "?"),
                            "Title: " .. tostring(t.title or ""),
                            "Status: " .. tostring(t.status or "unknown"),
                            "Prompt: " .. tostring(t.prompt or ""),
                            "Created: " .. tostring(t.createdAt or "-"),
                        }
                        vim.api.nvim_buf_set_lines(self.state.bufnr, 0, -1, false, lines)
                    end,
                }),
                attach_mappings = function(prompt_bufnr)
                    actions.select_default:replace(function()
                        actions.close(prompt_bufnr)
                        local sel = action_state.get_selected_entry()
                        if sel then
                            local t = sel.value
                            local id = tostring(t.id or t.taskId or "")
                            vim.ui.select({ "start", "approve", "cancel", "retry", "replay", "show" }, { prompt = "Action for task " .. id .. ":" }, function(choice)
                                if not choice then return end
                                if choice == "show" then
                                    M.get({ taskId = id }, function(r, e) vim.schedule(function()
                                        if e then vim.notify("[poor-cli] " .. vim.inspect(e), vim.log.levels.ERROR); return end
                                        open_scratch("[poor-cli task " .. id .. "]", vim.inspect(r), "lua")
                                    end) end)
                                else
                                    local method_map = { start = "startTask", approve = "approveTask", cancel = "cancelTask", retry = "retryTask", replay = "replayTask" }
                                    rpc.request("poor-cli/" .. method_map[choice], { taskId = id }, function(r, e) vim.schedule(function()
                                        if e then vim.notify("[poor-cli] " .. vim.inspect(e), vim.log.levels.ERROR)
                                        else vim.notify("[poor-cli] task " .. id .. " " .. choice .. " ok", vim.log.levels.INFO) end
                                    end) end)
                                end
                            end)
                        end
                    end)
                    return true
                end,
            }):find()
        end)
    end)
end

function M.setup()
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    create_command("PoorCliTasks", function()
        M.list({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR); return end
            local tasks = (result or {}).tasks or {}
            local lines = { "# tasks", "" }
            for _, t in ipairs(tasks) do table.insert(lines, format_task(t)) end
            if #tasks == 0 then table.insert(lines, "no tasks found") end
            open_scratch("[poor-cli tasks]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { desc = "List tasks" })
    create_command("PoorCliTaskCreate", function()
        vim.ui.input({ prompt = "Task title: " }, function(title)
            if not title or title == "" then return end
            vim.ui.input({ prompt = "Task prompt: " }, function(prompt)
                if not prompt or prompt == "" then return end
                M.create({ title = title, prompt = prompt }, function(_, err) vim.schedule(function()
                    if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR)
                    else vim.notify("[poor-cli] task created", vim.log.levels.INFO) end
                end) end)
            end)
        end)
    end, { desc = "Create task" })
    create_command("PoorCliTaskStart", function(opts)
        M.start({ taskId = opts.args }, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] task started", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Start task" })
    create_command("PoorCliTaskApprove", function(opts)
        M.approve({ taskId = opts.args }, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] task approved", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Approve task" })
    create_command("PoorCliTaskCancel", function(opts)
        M.cancel({ taskId = opts.args }, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] task cancelled", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Cancel task" })
    create_command("PoorCliTaskRetry", function(opts)
        M.retry({ taskId = opts.args }, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] task retried", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Retry task" })
    create_command("PoorCliTaskReplay", function(opts)
        M.replay({ taskId = opts.args }, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] task replayed", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Replay task" })
    create_command("PoorCliTaskShow", function(opts)
        M.get({ taskId = opts.args }, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR); return end
            open_scratch("[poor-cli task " .. opts.args .. "]", vim.inspect(result), "lua")
        end) end)
    end, { nargs = 1, desc = "Show task details" })
    create_command("PoorCliTasksPicker", function() M.open_picker() end, { desc = "Browse tasks with Telescope" })
end

return M
