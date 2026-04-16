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

-- ─────── History (picker — see history_browser.open_picker) ───────
local function build_history_panel()
    return {
        toggle = function() require("poor-cli.history_browser").open_picker() end,
        open = function() require("poor-cli.history_browser").open_picker() end,
        close = function() end,
        refresh = function() end,
        win = nil,
        buf = nil,
    }
end

-- ─────── Checkpoints (picker — see checkpoints_ext.open_picker) ───────
local function build_checkpoints_panel()
    return {
        toggle = function() require("poor-cli.checkpoints_ext").open_picker() end,
        open = function() require("poor-cli.checkpoints_ext").open_picker() end,
        close = function() end,
        refresh = function() end,
        win = nil,
        buf = nil,
    }
end

-- ─────── Queue (picker — see queue.open_picker) ───────
local function build_queue_panel()
    return {
        toggle = function() require("poor-cli.queue").open_picker() end,
        open = function() require("poor-cli.queue").open_picker() end,
        close = function() end,
        refresh = function() end,
        win = nil,
        buf = nil,
    }
end

-- ─────── Memory (picker — see memory_picker.open) ───────
local function build_memory_panel()
    return {
        toggle = function() require("poor-cli.memory_picker").open() end,
        open = function() require("poor-cli.memory_picker").open() end,
        close = function() end,
        refresh = function() end,
        win = nil,
        buf = nil,
    }
end

-- ───────────────────────── Sessions ─────────────────────────
local function build_sessions_panel()
    local panel
    local width, height = sidebar_dims()

    local function id_from_session_line(line)
        if not line then return nil end
        return line:match("^[%s●]*(%S+)$")
    end

    panel = base.new_panel({
        name = "[poor-cli sessions]",
        width = width,
        height = height,
        position = "right",
        keymaps = {
            ["<CR>"] = function()
                local id = id_from_session_line(vim.api.nvim_get_current_line())
                if not id or id == "?" or id == "Active:" then return end
                rpc.request("poor-cli/switchSession", { sessionId = id }, function(_, e) vim.schedule(function()
                    if e then notify(vim.inspect(e), vim.log.levels.ERROR)
                    else notify("switched to " .. id, vim.log.levels.INFO); panel.refresh() end
                end) end)
            end,
            ["f"] = function()
                local id = id_from_session_line(vim.api.nvim_get_current_line())
                if not id or id == "?" or id == "Active:" then return end
                rpc.request("poor-cli/forkSession", { sessionId = id }, function(_, e) vim.schedule(function()
                    if e then notify(vim.inspect(e), vim.log.levels.ERROR)
                    else notify("forked " .. id, vim.log.levels.INFO); panel.refresh() end
                end) end)
            end,
            ["x"] = function()
                local id = id_from_session_line(vim.api.nvim_get_current_line())
                if not id or id == "?" or id == "Active:" then return end
                rpc.request("poor-cli/destroySession", { sessionId = id }, function(_, e) vim.schedule(function()
                    if e then notify(vim.inspect(e), vim.log.levels.ERROR)
                    else notify("destroyed " .. id, vim.log.levels.INFO); panel.refresh() end
                end) end)
            end,
        },
        on_refresh = function(render_now)
            render_now()
            fetch("poor-cli/listSessions", {}, "sessions", panel)
        end,
        render = function()
            local lines = { "# poor-cli Sessions", "", "<CR> switch · f fork · x destroy · r refresh · q close", "" }
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
    local width, height = sidebar_dims()

    local function automation_id()
        local line = vim.api.nvim_get_current_line()
        return line and line:match("%((%S-)%)$")
    end

    panel = base.new_panel({
        name = "[poor-cli automations]",
        width = width,
        height = height,
        position = "right",
        keymaps = {
            ["<CR>"] = function()
                local id = automation_id()
                if not id then return end
                rpc.request("poor-cli/runAutomationNow", { automationId = id }, function(_, e) vim.schedule(function()
                    if e then notify(vim.inspect(e), vim.log.levels.ERROR)
                    else notify("triggered " .. id, vim.log.levels.INFO); panel.refresh() end
                end) end)
            end,
            ["t"] = function()
                local id = automation_id()
                if not id then return end
                local cache = (panel._cache or {}).automations or {}
                local enabled = true
                for _, a in ipairs(cache.automations or {}) do
                    if tostring(a.automationId) == id then enabled = not a.enabled; break end
                end
                rpc.request("poor-cli/setAutomationEnabled", { automationId = id, enabled = enabled }, function(_, e) vim.schedule(function()
                    if e then notify(vim.inspect(e), vim.log.levels.ERROR)
                    else notify((enabled and "enabled " or "disabled ") .. id, vim.log.levels.INFO); panel.refresh() end
                end) end)
            end,
            ["h"] = function()
                local id = automation_id()
                if not id then return end
                rpc.request("poor-cli/getAutomationHistory", { automationId = id }, function(r, e) vim.schedule(function()
                    if e then notify(vim.inspect(e), vim.log.levels.ERROR); return end
                    show_detail("[poor-cli automation history " .. id .. "]", r)
                end) end)
            end,
        },
        on_refresh = function(render_now)
            render_now()
            fetch("poor-cli/listAutomations", {}, "automations", panel)
        end,
        render = function()
            local lines = { "# poor-cli Automations", "", "<CR> run · t toggle · h history · r refresh · q close", "" }
            local data = (panel._cache or {}).automations
            section(lines, "Scheduled")
            if not data then empty(lines, "loading…")
            elseif data.error then empty(lines, "error: " .. data.error)
            else
                local items = data.automations or {}
                if vim.tbl_isempty(items) then empty(lines, "no automations")
                else
                    for _, a in ipairs(items) do
                        local mark = a.enabled and "●" or "○"
                        table.insert(lines, string.format("- %s **%s** (%s)", mark, a.name or "?", a.automationId or "?"))
                        if a.scheduleSummary and a.scheduleSummary ~= "" then
                            table.insert(lines, "    schedule: " .. tostring(a.scheduleSummary))
                        end
                        if a.nextRunAt then
                            table.insert(lines, "    next run: " .. tostring(a.nextRunAt))
                        end
                        if a.lastRunStatus and a.lastRunStatus ~= "" then
                            table.insert(lines, string.format("    last run: %s %s %s",
                                icon_for(a.lastRunStatus), tostring(a.lastRunStatus), tostring(a.lastRunAt or "")))
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
-- Return the set of panel objects matching `names`, or all panels if names is empty.
local function select_panels(names)
    if not names or #names == 0 then return M.panels end
    local sel = {}
    for _, n in ipairs(names) do
        if M.panels[n] then sel[n] = M.panels[n] end
    end
    return sel
end

local function apply(method, names)
    for _, p in pairs(select_panels(names)) do
        pcall(p[method])
    end
end

local function panel_name_complete()
    local out = {}
    for n, _ in pairs(M.panels) do table.insert(out, n) end
    table.sort(out)
    return out
end

function M.setup()
    M.panels.tasks = build_tasks_panel()
    M.panels.agents = build_agents_panel()
    M.panels.history = build_history_panel()
    M.panels.checkpoints = build_checkpoints_panel()
    M.panels.queue = build_queue_panel()
    M.panels.memory = build_memory_panel()
    M.panels.sessions = build_sessions_panel()
    M.panels.automations = build_automations_panel()

    require("poor-cli.command_spec").install("panel", {
        desc = "Open, close, or toggle poor-cli info panels",
        verb_names = { "open", "close", "toggle" },
        verbs = {
            open   = function(fargs) apply("open", fargs) end,
            close  = function(fargs) apply("close", fargs) end,
            toggle = function(fargs) apply("toggle", fargs) end,
        },
        arg_complete = {
            open   = panel_name_complete,
            close  = panel_name_complete,
            toggle = panel_name_complete,
        },
    })

    -- live refresh on status changes
    base.subscribe("PoorCLIPanelsRefresh", { "PoorCLIStatusChanged" }, function()
        for _, p in pairs(M.panels) do
            if p.win and vim.api.nvim_win_is_valid(p.win) then
                p.refresh()
            end
        end
    end)
end

-- Exported for tests and for :checkhealth.
M._select_panels = select_panels
M._panel_name_complete = panel_name_complete

return M
