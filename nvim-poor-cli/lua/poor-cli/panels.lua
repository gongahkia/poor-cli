-- poor-cli/panels.lua
-- Info panels: tasks, agents, history, checkpoints, queue, memory, sessions, automations.
-- Tasks/agents/sessions/automations open as right-side sidebar floats (with row actions).
-- Checkpoints/queue/memory/history open through pickers.pick. Refresh via r, close via q/<Esc>.

local base = require("poor-cli.panel_base")
local rpc = require("poor-cli.rpc")

local M = {}
M.panels = {} -- name → panel

local function section(lines, title)
    table.insert(lines, "## " .. title)
    table.insert(lines, "")
end

local function empty(lines, msg)
    table.insert(lines, "_" .. (msg or "no entries") .. "_")
end

local status_icon = {
    pending = "○",
    running = "●",
    completed = "✓",
    success = "✓",
    succeeded = "✓",
    failed = "✗",
    cancelled = "⊘",
    canceled = "⊘",
    ready = "◇",
    scheduled = "⏲",
}

local function icon_for(status)
    return status_icon[tostring(status):lower()] or "·"
end

local function sidebar_dims()
    return 56, math.max(20, vim.o.lines - 4)
end

local function id_from_line(line)
    if not line then return nil end
    return line:match("^%-%s+%S+%s+%[[^%]]+%]%s+(%S+)") -- "- ICON [status] id"
        or line:match("^%-%s+%[[^%]]+%]%s+(%S+)")       -- "- [status] id"
        or line:match("^%-%s+(%S+)")                     -- "- id"
end

local function current_id()
    local line = vim.api.nvim_get_current_line()
    return id_from_line(line)
end

local function show_detail(title, value)
    local float_win = require("poor-cli.float_win")
    local lines = vim.split(vim.inspect(value), "\n", { plain = true })
    float_win.open_lines(lines, {
        filetype = "lua",
        name = title,
        title = " " .. title:gsub("^%[", ""):gsub("%]$", "") .. " ",
        width = 0.6,
        height = 0.6,
        position = "center",
    })
end

local function notify(msg, level)
    require("poor-cli.notify").notify("[poor-cli] " .. msg, level)
end

local function fetch(method, params, into_key, panel)
    panel._cache = panel._cache or {}
    panel._fetch_in_flight = panel._fetch_in_flight or {}
    if panel._fetch_in_flight[method] then return end
    panel._fetch_in_flight[method] = true
    rpc.request(method, params or {}, function(result, err)
        vim.schedule(function()
            panel._fetch_in_flight[method] = false
            if err then
                panel._cache[into_key] = { error = rpc.format_error(err) }
            else
                panel._cache[into_key] = result or {}
            end
            panel.refresh()
        end)
    end)
end

-- ───────────────────────── Tasks ─────────────────────────
local function build_tasks_panel()
    local panel
    local width, height = sidebar_dims()
    panel = base.new_panel({
        name = "[poor-cli tasks]",
        width = width,
        height = height,
        position = "right",
        keymaps = {
            ["<CR>"] = function()
                local id = current_id()
                if not id or id == "?" then return end
                rpc.request("poor-cli/getTask", { taskId = id }, function(r, e) vim.schedule(function()
                    if e then notify(vim.inspect(e), vim.log.levels.ERROR); return end
                    show_detail("[poor-cli task " .. id .. "]", r)
                end) end)
            end,
            ["x"] = function()
                local id = current_id()
                if not id or id == "?" then return end
                rpc.request("poor-cli/cancelTask", { taskId = id }, function(_, e) vim.schedule(function()
                    if e then notify(vim.inspect(e), vim.log.levels.ERROR)
                    else notify("task " .. id .. " cancelled", vim.log.levels.INFO); panel.refresh() end
                end) end)
            end,
        },
        on_refresh = function(render_now)
            render_now()
            fetch("poor-cli/listTasks", {}, "tasks", panel)
        end,
        render = function()
            local lines = { "# poor-cli Tasks", "", "<CR> detail · x cancel · r refresh · q close", "" }
            local data = (panel._cache or {}).tasks
            section(lines, "Active & recent")
            if not data then
                empty(lines, "loading…")
            elseif data.error then
                empty(lines, "error: " .. data.error)
            else
                local items = data.tasks or {}
                if vim.tbl_isempty(items) then
                    empty(lines, "no tasks")
                else
                    for _, t in ipairs(items) do
                        local created = t.createdAt or ""
                        table.insert(lines, string.format("- %s [%s] %s",
                            icon_for(t.status), t.status or "?", t.taskId or "?"))
                        if t.title and t.title ~= "" then
                            table.insert(lines, "    " .. t.title)
                        end
                        if created ~= "" then
                            table.insert(lines, "    created: " .. tostring(created))
                        end
                    end
                end
            end
            return lines
        end,
    })
    return panel
end

-- ───────────────────────── Agents ─────────────────────────
local function build_agents_panel()
    local panel
    local width, height = sidebar_dims()
    panel = base.new_panel({
        name = "[poor-cli agents]",
        width = width,
        height = height,
        position = "right",
        keymaps = {
            ["<CR>"] = function()
                local id = current_id()
                if not id or id == "?" then return end
                rpc.request("poor-cli/getAgentLogs", { agentId = id }, function(r, e) vim.schedule(function()
                    if e then notify(vim.inspect(e), vim.log.levels.ERROR); return end
                    show_detail("[poor-cli agent logs " .. id .. "]", r)
                end) end)
            end,
            ["x"] = function()
                local id = current_id()
                if not id or id == "?" then return end
                rpc.request("poor-cli/cancelAgent", { agentId = id }, function(_, e) vim.schedule(function()
                    if e then notify(vim.inspect(e), vim.log.levels.ERROR)
                    else notify("agent " .. id .. " cancelled", vim.log.levels.INFO); panel.refresh() end
                end) end)
            end,
        },
        on_refresh = function(render_now)
            render_now()
            fetch("poor-cli/listAgents", {}, "agents", panel)
        end,
        render = function()
            local lines = { "# poor-cli Agents", "", "<CR> logs · x cancel · r refresh · q close", "" }
            local data = (panel._cache or {}).agents
            section(lines, "Background agents")
            if not data then empty(lines, "loading…")
            elseif data.error then empty(lines, "error: " .. data.error)
            else
                local items = data.agents or {}
                if vim.tbl_isempty(items) then empty(lines, "no agents")
                else
                    for _, a in ipairs(items) do
                        local prompt = tostring(a.prompt or ""):sub(1, 80)
                        table.insert(lines, string.format("- %s [%s] %s",
                            icon_for(a.status), a.status or "?", a.agentId or "?"))
                        if prompt ~= "" then
                            table.insert(lines, "    " .. prompt)
                        end
                        if a.createdAt then
                            table.insert(lines, "    created: " .. tostring(a.createdAt))
                        end
                    end
                end
            end
            return lines
        end,
    })
    return panel
end

-- ───────────────────────── History ─────────────────────────
local function build_history_panel()
    local panel
    panel = base.new_panel({
        name = "[poor-cli history]",
        width = 80,
        on_refresh = function(render_now)
            render_now()
            fetch("poor-cli/listHistory", { count = 30 }, "history", panel)
        end,
        render = function()
            local lines = { "# poor-cli History", "", "Press q to close, r to refresh. `:PoorCLIHistorySearch <q>` to search.", "" }
            local data = (panel._cache or {}).history
            if data and data.sessionId then
                table.insert(lines, "Session: `" .. tostring(data.sessionId) .. "`")
                table.insert(lines, "")
            end
            section(lines, "Recent messages")
            if not data then empty(lines, "loading…")
            elseif data.error then empty(lines, "error: " .. data.error)
            else
                local items = data.messages or {}
                if vim.tbl_isempty(items) then empty(lines, "no messages")
                else
                    for _, m in ipairs(items) do
                        local content = tostring(m.content or ""):gsub("\n", " "):sub(1, 120)
                        table.insert(lines, string.format("- **%s** @ %s", m.role or "?", tostring(m.timestamp or "")))
                        if content ~= "" then
                            table.insert(lines, "    " .. content)
                        end
                    end
                end
            end
            return lines
        end,
    })
    return panel
end

-- ───────────────────────── Checkpoints ─────────────────────────
local function build_checkpoints_panel()
    local panel
    panel = base.new_panel({
        name = "[poor-cli checkpoints]",
        width = 70,
        on_refresh = function(render_now)
            render_now()
            fetch("poor-cli/listCheckpoints", {}, "checkpoints", panel)
        end,
        render = function()
            local lines = { "# poor-cli Checkpoints", "", "Press q to close, r to refresh. `:PoorCLICheckpointPreview <id>` and `Restore` for actions.", "" }
            local data = (panel._cache or {}).checkpoints
            section(lines, "Recent")
            if not data then empty(lines, "loading…")
            elseif data.error then empty(lines, "error: " .. data.error)
            elseif data.available == false then
                empty(lines, "checkpoint system unavailable")
            else
                local items = data.checkpoints or {}
                if vim.tbl_isempty(items) then empty(lines, "no checkpoints")
                else
                    for _, cp in ipairs(items) do
                        local tags = (type(cp.tags) == "table" and #cp.tags > 0) and (" [" .. table.concat(cp.tags, ",") .. "]") or ""
                        table.insert(lines, string.format("- %s%s", cp.checkpointId or "?", tags))
                        if cp.description and cp.description ~= "" then
                            table.insert(lines, "    " .. cp.description)
                        end
                        table.insert(lines, string.format("    %s · %d file(s) · %.1f KB", tostring(cp.createdAt or ""), cp.fileCount or 0, (cp.totalSizeBytes or 0) / 1024))
                    end
                end
                if data.storagePath then
                    table.insert(lines, "")
                    table.insert(lines, "Storage: `" .. tostring(data.storagePath) .. "`")
                end
            end
            return lines
        end,
    })
    return panel
end

-- ───────────────────────── Queue ─────────────────────────
local function build_queue_panel()
    local panel
    panel = base.new_panel({
        name = "[poor-cli queue]",
        width = 60,
        render = function()
            local lines = { "# poor-cli Queue", "", "Press q to close, r to refresh.", "" }
            section(lines, "Queued prompts (local)")
            local ok, queue_mod = pcall(require, "poor-cli.queue")
            if ok and queue_mod and queue_mod.list then
                local items = queue_mod.list() or {}
                if vim.tbl_isempty(items) then empty(lines, "queue empty")
                else
                    for i, q in ipairs(items) do
                        table.insert(lines, string.format("%d. %s", i, tostring(q):sub(1, 80)))
                    end
                end
            else
                empty(lines, "queue module unavailable")
            end
            return lines
        end,
    })
    return panel
end

-- ───────────────────────── Memory ─────────────────────────
local function build_memory_panel()
    local panel
    panel = base.new_panel({
        name = "[poor-cli memory]",
        width = 70,
        on_refresh = function(render_now)
            render_now()
            fetch("poor-cli/memoryList", {}, "memory", panel)
        end,
        render = function()
            local lines = { "# poor-cli Memory", "", "Press q to close, r to refresh. `:PoorCLIMemorySave <text>` to add.", "" }
            local data = (panel._cache or {}).memory
            section(lines, "Persistent entries")
            if not data then empty(lines, "loading…")
            elseif data.error then empty(lines, "error: " .. data.error)
            else
                local items = data.memories or {}
                if vim.tbl_isempty(items) then empty(lines, "no memories")
                else
                    for _, m in ipairs(items) do
                        table.insert(lines, string.format("- [%s] **%s**", m.type or "?", m.name or "?"))
                        if m.description and m.description ~= "" then
                            table.insert(lines, "    " .. m.description)
                        end
                        if m.filename then
                            table.insert(lines, "    file: " .. tostring(m.filename))
                        end
                    end
                end
            end
            return lines
        end,
    })
    return panel
end

-- ───────────────────────── Sessions ─────────────────────────
local function build_sessions_panel()
    local panel
    panel = base.new_panel({
        name = "[poor-cli sessions]",
        width = 80,
        on_refresh = function(render_now)
            render_now()
            fetch("poor-cli/listSessions", {}, "sessions", panel)
        end,
        render = function()
            local lines = { "# poor-cli Sessions", "", "Press q to close, r to refresh. `:PoorCLISessionSwitch <id>` to switch.", "" }
            local data = (panel._cache or {}).sessions
            section(lines, "Sessions")
            if not data then empty(lines, "loading…")
            elseif data.error then empty(lines, "error: " .. data.error)
            else
                local items = data.sessions or {}
                if vim.tbl_isempty(items) then empty(lines, "no sessions")
                else
                    if data.activeSessionId then
                        table.insert(lines, "Active: `" .. tostring(data.activeSessionId) .. "`")
                        table.insert(lines, "")
                    end
                    for _, s in ipairs(items) do
                        local marker = s.isActive and "● " or "  "
                        table.insert(lines, string.format("%s%s", marker, s.sessionId or "?"))
                        table.insert(lines, string.format("    model: %s · %d msg(s)", tostring(s.model or "?"), s.messageCount or 0))
                        if s.startedAt then
                            local ended = s.endedAt and (" → " .. tostring(s.endedAt)) or ""
                            table.insert(lines, "    " .. tostring(s.startedAt) .. ended)
                        end
                    end
                end
            end
            return lines
        end,
    })
    return panel
end

-- ───────────────────────── Automations ─────────────────────────
local function build_automations_panel()
    local panel
    panel = base.new_panel({
        name = "[poor-cli automations]",
        width = 80,
        on_refresh = function(render_now)
            render_now()
            fetch("poor-cli/listAutomations", {}, "automations", panel)
        end,
        render = function()
            local lines = { "# poor-cli Automations", "", "Press q to close, r to refresh. `:PoorCLIAutomationEnable/Disable/Run <id>` for actions.", "" }
            local data = (panel._cache or {}).automations
            section(lines, "Scheduled")
            if not data then empty(lines, "loading…")
            elseif data.error then empty(lines, "error: " .. data.error)
            else
                local items = data.automations or {}
                if vim.tbl_isempty(items) then empty(lines, "no automations")
                else
                    for _, a in ipairs(items) do
                        local enabled = a.enabled and "on" or "off"
                        table.insert(lines, string.format("- [%s] **%s** (%s)", enabled, a.name or "?", a.automationId or "?"))
                        if a.scheduleSummary and a.scheduleSummary ~= "" then
                            table.insert(lines, "    schedule: " .. tostring(a.scheduleSummary))
                        end
                        if a.nextRunAt then
                            table.insert(lines, "    next run: " .. tostring(a.nextRunAt))
                        end
                        if a.lastRunStatus and a.lastRunStatus ~= "" then
                            table.insert(lines, string.format("    last run: %s %s", tostring(a.lastRunStatus), tostring(a.lastRunAt or "")))
                        end
                    end
                end
            end
            return lines
        end,
    })
    return panel
end

-- ───────────────────────── Registration ─────────────────────────
function M.setup()
    M.panels.tasks = build_tasks_panel()
    M.panels.agents = build_agents_panel()
    M.panels.history = build_history_panel()
    M.panels.checkpoints = build_checkpoints_panel()
    M.panels.queue = build_queue_panel()
    M.panels.memory = build_memory_panel()
    M.panels.sessions = build_sessions_panel()
    M.panels.automations = build_automations_panel()

    local function create_command(name, fn, opts)
        pcall(vim.api.nvim_del_user_command, name)
        vim.api.nvim_create_user_command(name, fn, opts or {})
    end

    create_command("PoorCLITasksPanel",       function() M.panels.tasks.toggle() end,       { desc = "Toggle poor-cli tasks panel" })
    create_command("PoorCLIAgentsPanel",      function() M.panels.agents.toggle() end,      { desc = "Toggle poor-cli agents panel" })
    create_command("PoorCLIHistoryPanel",     function() M.panels.history.toggle() end,     { desc = "Toggle poor-cli history panel" })
    create_command("PoorCLICheckpointsPanel", function() M.panels.checkpoints.toggle() end, { desc = "Toggle poor-cli checkpoints panel" })
    create_command("PoorCLIQueuePanel",       function() M.panels.queue.toggle() end,       { desc = "Toggle poor-cli queue panel" })
    create_command("PoorCLIMemoryPanel",      function() M.panels.memory.toggle() end,      { desc = "Toggle poor-cli memory panel" })
    create_command("PoorCLISessionsPanel",    function() M.panels.sessions.toggle() end,    { desc = "Toggle poor-cli sessions panel" })
    create_command("PoorCLIAutomationsPanel", function() M.panels.automations.toggle() end, { desc = "Toggle poor-cli automations panel" })

    -- live refresh on status changes
    base.subscribe("PoorCLIPanelsRefresh", { "PoorCLIStatusChanged" }, function()
        for _, p in pairs(M.panels) do
            if p.win and vim.api.nvim_win_is_valid(p.win) then
                p.refresh()
            end
        end
    end)
end

return M
