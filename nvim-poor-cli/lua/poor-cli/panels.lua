-- poor-cli/panels.lua
-- Read-only info panels: tasks, agents, history, checkpoints, queue, memory, sessions, automations.
-- Each panel opens a right-side vertical split, refreshes via r, closes via q.

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
    panel = base.new_panel({
        name = "[poor-cli tasks]",
        width = 70,
        on_refresh = function(render_now)
            render_now()
            fetch("poor-cli/listTasks", {}, "tasks", panel)
        end,
        render = function()
            local lines = { "# poor-cli Tasks", "", "Press q to close, r to refresh.", "" }
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
                        table.insert(lines, string.format("- [%s] %s", t.status or "?", t.taskId or "?"))
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
    panel = base.new_panel({
        name = "[poor-cli agents]",
        width = 70,
        on_refresh = function(render_now)
            render_now()
            fetch("poor-cli/listAgents", {}, "agents", panel)
        end,
        render = function()
            local lines = { "# poor-cli Agents", "", "Press q to close, r to refresh.", "" }
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
                        table.insert(lines, string.format("- [%s] %s", a.status or "?", a.agentId or "?"))
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
            local lines = { "# poor-cli History", "", "Press q to close, r to refresh. `:PoorCliHistorySearch <q>` to search.", "" }
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
            local lines = { "# poor-cli Checkpoints", "", "Press q to close, r to refresh. `:PoorCliCheckpointPreview <id>` and `Restore` for actions.", "" }
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
            local lines = { "# poor-cli Memory", "", "Press q to close, r to refresh. `:PoorCliMemorySave <text>` to add.", "" }
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
            local lines = { "# poor-cli Sessions", "", "Press q to close, r to refresh. `:PoorCliSessionSwitch <id>` to switch.", "" }
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
            local lines = { "# poor-cli Automations", "", "Press q to close, r to refresh. `:PoorCliAutomationEnable/Disable/Run <id>` for actions.", "" }
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

    create_command("PoorCliTasksPanel",       function() M.panels.tasks.toggle() end,       { desc = "Toggle poor-cli tasks panel" })
    create_command("PoorCliAgentsPanel",      function() M.panels.agents.toggle() end,      { desc = "Toggle poor-cli agents panel" })
    create_command("PoorCliHistoryPanel",     function() M.panels.history.toggle() end,     { desc = "Toggle poor-cli history panel" })
    create_command("PoorCliCheckpointsPanel", function() M.panels.checkpoints.toggle() end, { desc = "Toggle poor-cli checkpoints panel" })
    create_command("PoorCliQueuePanel",       function() M.panels.queue.toggle() end,       { desc = "Toggle poor-cli queue panel" })
    create_command("PoorCliMemoryPanel",      function() M.panels.memory.toggle() end,      { desc = "Toggle poor-cli memory panel" })
    create_command("PoorCliSessionsPanel",    function() M.panels.sessions.toggle() end,    { desc = "Toggle poor-cli sessions panel" })
    create_command("PoorCliAutomationsPanel", function() M.panels.automations.toggle() end, { desc = "Toggle poor-cli automations panel" })

    -- live refresh on status changes
    base.subscribe("PoorCliPanelsRefresh", { "PoorCliStatusChanged" }, function()
        for _, p in pairs(M.panels) do
            if p.win and vim.api.nvim_win_is_valid(p.win) then
                p.refresh()
            end
        end
    end)
end

return M
