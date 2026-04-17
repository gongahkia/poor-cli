-- poor-cli/panels/runtime.lua
-- Unified runtime inspector: tabs for tasks / agents / sessions / automations.
-- Each tab is a { title, render(cache), on_refresh(set_cache), keymaps } bag.

local rpc = require("poor-cli.rpc")

local M = {}

M.buf = nil
M.win = nil
M.ns = vim.api.nvim_create_namespace("poor-cli_runtime")
M.active = "tasks"
M.line_id = {}
M.cache = {}
M._fetch_in_flight = {}

local TAB_ORDER = { "tasks", "agents", "sessions", "automations" }

local STATUS_ICON = {
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
    return STATUS_ICON[tostring(status):lower()] or "·"
end

local function notify(msg, level)
    require("poor-cli.notify").notify("[poor-cli] " .. msg, level)
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

local function fetch(method, key)
    if M._fetch_in_flight[key] then return end
    M._fetch_in_flight[key] = true
    rpc.request(method, {}, function(result, err)
        vim.schedule(function()
            M._fetch_in_flight[key] = false
            if err then
                M.cache[key] = { error = rpc.format_error(err) }
            else
                M.cache[key] = result or {}
            end
            M.render()
        end)
    end)
end

local function current_id()
    local line = vim.api.nvim_win_get_cursor(M.win or 0)[1]
    return M.line_id[line]
end

-- ───────────────── Tabs ─────────────────

local function tab_tasks()
    return {
        title = "tasks",
        fetch = function() fetch("poor-cli/listTasks", "tasks") end,
        render = function(cache)
            local lines, row_id = {}, {}
            local data = cache.tasks
            if not data then
                table.insert(lines, "loading…")
            elseif data.error then
                table.insert(lines, "error: " .. data.error)
            else
                local items = data.tasks or {}
                if vim.tbl_isempty(items) then
                    table.insert(lines, "no tasks")
                else
                    for _, t in ipairs(items) do
                        table.insert(lines, string.format("%s [%s] %-12s %s",
                            icon_for(t.status), t.status or "?", t.taskId or "?",
                            t.title or ""))
                        row_id[#lines] = t.taskId
                        if t.createdAt then
                            table.insert(lines, "    created: " .. tostring(t.createdAt))
                            row_id[#lines] = t.taskId
                        end
                    end
                end
            end
            return lines, row_id
        end,
        keymaps = {
            ["<CR>"] = function()
                local id = current_id()
                if not id then return end
                rpc.request("poor-cli/getTask", { taskId = id }, function(r, e) vim.schedule(function()
                    if e then notify(vim.inspect(e), vim.log.levels.ERROR); return end
                    show_detail("[poor-cli task " .. id .. "]", r)
                end) end)
            end,
            ["x"] = function()
                local id = current_id()
                if not id then return end
                rpc.request("poor-cli/cancelTask", { taskId = id }, function(_, e) vim.schedule(function()
                    if e then notify(vim.inspect(e), vim.log.levels.ERROR)
                    else notify("task " .. id .. " cancelled", vim.log.levels.INFO); M.refresh() end
                end) end)
            end,
        },
        footer = "<CR> detail  x cancel  gt/gT tabs  r refresh  q close",
    }
end

local function tab_agents()
    return {
        title = "agents",
        fetch = function() fetch("poor-cli/listAgents", "agents") end,
        render = function(cache)
            local lines, row_id = {}, {}
            local data = cache.agents
            if not data then
                table.insert(lines, "loading…")
            elseif data.error then
                table.insert(lines, "error: " .. data.error)
            else
                local items = data.agents or {}
                if vim.tbl_isempty(items) then
                    table.insert(lines, "no agents")
                else
                    for _, a in ipairs(items) do
                        local prompt = tostring(a.prompt or ""):sub(1, 80)
                        table.insert(lines, string.format("%s [%s] %-12s %s",
                            icon_for(a.status), a.status or "?", a.agentId or "?",
                            prompt))
                        row_id[#lines] = a.agentId
                        if a.createdAt then
                            table.insert(lines, "    created: " .. tostring(a.createdAt))
                            row_id[#lines] = a.agentId
                        end
                    end
                end
            end
            return lines, row_id
        end,
        keymaps = {
            ["<CR>"] = function()
                local id = current_id()
                if not id then return end
                rpc.request("poor-cli/getAgentLogs", { agentId = id }, function(r, e) vim.schedule(function()
                    if e then notify(vim.inspect(e), vim.log.levels.ERROR); return end
                    show_detail("[poor-cli agent " .. id .. "]", r)
                end) end)
            end,
            ["x"] = function()
                local id = current_id()
                if not id then return end
                rpc.request("poor-cli/cancelAgent", { agentId = id }, function(_, e) vim.schedule(function()
                    if e then notify(vim.inspect(e), vim.log.levels.ERROR)
                    else notify("agent " .. id .. " cancelled", vim.log.levels.INFO); M.refresh() end
                end) end)
            end,
        },
        footer = "<CR> logs  x cancel  gt/gT tabs  r refresh  q close",
    }
end

local function tab_sessions()
    return {
        title = "sessions",
        fetch = function() fetch("poor-cli/listSessions", "sessions") end,
        render = function(cache)
            local lines, row_id = {}, {}
            local data = cache.sessions
            if not data then
                table.insert(lines, "loading…")
            elseif data.error then
                table.insert(lines, "error: " .. data.error)
            else
                local items = data.sessions or {}
                if vim.tbl_isempty(items) then
                    table.insert(lines, "no sessions")
                else
                    if data.activeSessionId then
                        table.insert(lines, "Active: " .. tostring(data.activeSessionId))
                        table.insert(lines, "")
                    end
                    for _, s in ipairs(items) do
                        local marker = s.isActive and "● " or "  "
                        table.insert(lines, marker .. (s.sessionId or "?"))
                        row_id[#lines] = s.sessionId
                        table.insert(lines, string.format("    model: %s · %d msg(s)",
                            tostring(s.model or "?"), s.messageCount or 0))
                        row_id[#lines] = s.sessionId
                        if s.startedAt then
                            local ended = s.endedAt and (" → " .. tostring(s.endedAt)) or ""
                            table.insert(lines, "    " .. tostring(s.startedAt) .. ended)
                            row_id[#lines] = s.sessionId
                        end
                    end
                end
            end
            return lines, row_id
        end,
        keymaps = {
            ["<CR>"] = function()
                local id = current_id()
                if not id or id == "Active:" then return end
                rpc.request("poor-cli/switchSession", { sessionId = id }, function(_, e) vim.schedule(function()
                    if e then notify(vim.inspect(e), vim.log.levels.ERROR)
                    else notify("switched to " .. id, vim.log.levels.INFO); M.refresh() end
                end) end)
            end,
            ["f"] = function()
                local id = current_id()
                if not id then return end
                rpc.request("poor-cli/forkSession", { sessionId = id }, function(_, e) vim.schedule(function()
                    if e then notify(vim.inspect(e), vim.log.levels.ERROR)
                    else notify("forked " .. id, vim.log.levels.INFO); M.refresh() end
                end) end)
            end,
            ["x"] = function()
                local id = current_id()
                if not id then return end
                rpc.request("poor-cli/destroySession", { sessionId = id }, function(_, e) vim.schedule(function()
                    if e then notify(vim.inspect(e), vim.log.levels.ERROR)
                    else notify("destroyed " .. id, vim.log.levels.INFO); M.refresh() end
                end) end)
            end,
        },
        footer = "<CR> switch  f fork  x destroy  gt/gT tabs  r refresh  q close",
    }
end

local function tab_automations()
    return {
        title = "automations",
        fetch = function() fetch("poor-cli/listAutomations", "automations") end,
        render = function(cache)
            local lines, row_id = {}, {}
            local data = cache.automations
            if not data then
                table.insert(lines, "loading…")
            elseif data.error then
                table.insert(lines, "error: " .. data.error)
            else
                local items = data.automations or {}
                if vim.tbl_isempty(items) then
                    table.insert(lines, "no automations")
                else
                    for _, a in ipairs(items) do
                        local mark = a.enabled and "●" or "○"
                        table.insert(lines, string.format("%s %s  (%s)",
                            mark, a.name or "?", a.automationId or "?"))
                        row_id[#lines] = a.automationId
                        if a.scheduleSummary and a.scheduleSummary ~= "" then
                            table.insert(lines, "    schedule: " .. tostring(a.scheduleSummary))
                            row_id[#lines] = a.automationId
                        end
                        if a.nextRunAt then
                            table.insert(lines, "    next: " .. tostring(a.nextRunAt))
                            row_id[#lines] = a.automationId
                        end
                        if a.lastRunStatus and a.lastRunStatus ~= "" then
                            table.insert(lines, string.format("    last: %s %s %s",
                                icon_for(a.lastRunStatus), tostring(a.lastRunStatus),
                                tostring(a.lastRunAt or "")))
                            row_id[#lines] = a.automationId
                        end
                    end
                end
            end
            return lines, row_id
        end,
        keymaps = {
            ["<CR>"] = function()
                local id = current_id()
                if not id then return end
                rpc.request("poor-cli/runAutomationNow", { automationId = id }, function(_, e) vim.schedule(function()
                    if e then notify(vim.inspect(e), vim.log.levels.ERROR)
                    else notify("triggered " .. id, vim.log.levels.INFO); M.refresh() end
                end) end)
            end,
            ["t"] = function()
                local id = current_id()
                if not id then return end
                local cache = M.cache.automations or {}
                local enabled = true
                for _, a in ipairs(cache.automations or {}) do
                    if tostring(a.automationId) == id then enabled = not a.enabled; break end
                end
                rpc.request("poor-cli/setAutomationEnabled", { automationId = id, enabled = enabled }, function(_, e) vim.schedule(function()
                    if e then notify(vim.inspect(e), vim.log.levels.ERROR)
                    else notify((enabled and "enabled " or "disabled ") .. id, vim.log.levels.INFO); M.refresh() end
                end) end)
            end,
            ["h"] = function()
                local id = current_id()
                if not id then return end
                rpc.request("poor-cli/getAutomationHistory", { automationId = id }, function(r, e) vim.schedule(function()
                    if e then notify(vim.inspect(e), vim.log.levels.ERROR); return end
                    show_detail("[poor-cli automation " .. id .. "]", r)
                end) end)
            end,
        },
        footer = "<CR> run  t toggle  h history  gt/gT tabs  r refresh  q close",
    }
end

M.tabs = {
    tasks = tab_tasks(),
    agents = tab_agents(),
    sessions = tab_sessions(),
    automations = tab_automations(),
}

local function tab_header()
    local parts = {}
    for _, name in ipairs(TAB_ORDER) do
        if name == M.active then
            table.insert(parts, "[" .. name:upper() .. "]")
        else
            table.insert(parts, " " .. name .. " ")
        end
    end
    return "  " .. table.concat(parts, " ")
end

function M.render()
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then return end
    local tab = M.tabs[M.active]
    local lines = { "# poor-cli runtime", tab_header(), "" }
    local tab_lines, tab_rows = tab.render(M.cache)
    for i, line in ipairs(tab_lines) do
        table.insert(lines, line)
        M.line_id[#lines] = tab_rows[i]
    end
    table.insert(lines, "")
    table.insert(lines, tab.footer)
    vim.bo[M.buf].modifiable = true
    vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, lines)
    vim.bo[M.buf].modifiable = false
    -- tab header highlight
    vim.api.nvim_buf_clear_namespace(M.buf, M.ns, 0, -1)
    local header = lines[2]
    local start = header:find("%[") or 0
    if start > 0 then
        local end_col = header:find("%]", start) or start
        vim.api.nvim_buf_set_extmark(M.buf, M.ns, 1, start - 1, {
            end_col = end_col,
            hl_group = "Title",
        })
    end
end

function M.refresh()
    M.line_id = {}
    local tab = M.tabs[M.active]
    if tab and tab.fetch then tab.fetch() end
    M.render()
end

local function rebind_tab_keymaps()
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then return end
    -- Strip previously-bound tab keys (single-char action keys set by tabs)
    for _, key in ipairs({ "<CR>", "x", "f", "t", "h" }) do
        pcall(vim.keymap.del, "n", key, { buffer = M.buf })
    end
    local tab = M.tabs[M.active]
    for lhs, fn in pairs(tab.keymaps or {}) do
        vim.keymap.set("n", lhs, fn, { buffer = M.buf, nowait = true, silent = true })
    end
end

function M.cycle_tab(direction)
    direction = direction or 1
    local idx = 1
    for i, name in ipairs(TAB_ORDER) do if name == M.active then idx = i; break end end
    idx = ((idx - 1 + direction) % #TAB_ORDER) + 1
    M.active = TAB_ORDER[idx]
    rebind_tab_keymaps()
    M.refresh()
end

function M.close()
    if M.win and vim.api.nvim_win_is_valid(M.win) then vim.api.nvim_win_close(M.win, true) end
    M.win = nil
end

function M.open(tab)
    if tab and M.tabs[tab] then M.active = tab end
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_set_current_win(M.win)
        rebind_tab_keymaps()
        M.refresh()
        return M.buf
    end
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then
        M.buf = vim.api.nvim_create_buf(false, true)
        vim.bo[M.buf].buftype = "nofile"
        vim.bo[M.buf].bufhidden = "hide"
        vim.bo[M.buf].swapfile = false
        vim.bo[M.buf].filetype = "markdown"
        vim.api.nvim_buf_set_name(M.buf, "[poor-cli runtime]")
    end
    local float_win = require("poor-cli.float_win")
    M.win = float_win.open(M.buf, {
        width = math.min(90, vim.o.columns - 4),
        height = math.max(24, math.floor(vim.o.lines * 0.8)),
        position = "right",
        title = " poor-cli runtime ",
        close_keys = {},
        wrap = false,
    })
    vim.keymap.set("n", "q", M.close, { buffer = M.buf, nowait = true })
    vim.keymap.set("n", "<Esc>", M.close, { buffer = M.buf, nowait = true })
    vim.keymap.set("n", "r", M.refresh, { buffer = M.buf, nowait = true })
    vim.keymap.set("n", "gt", function() M.cycle_tab(1) end, { buffer = M.buf, nowait = true })
    vim.keymap.set("n", "gT", function() M.cycle_tab(-1) end, { buffer = M.buf, nowait = true })
    rebind_tab_keymaps()
    M.refresh()
    return M.buf
end

function M.toggle(tab)
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        if tab and tab ~= M.active and M.tabs[tab] then
            M.active = tab
            rebind_tab_keymaps()
            M.refresh()
        else
            M.close()
        end
    else
        M.open(tab)
    end
end

return M
