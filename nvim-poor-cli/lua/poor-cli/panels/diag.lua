-- poor-cli/panels/diag.lua
-- Unified diagnostics dashboard. Replaces the vim.inspect() dumps from
-- :PoorCLIDiag mcp-health / docker-sandbox / :PoorCLIService status /
-- :PoorCLIConfig instructions / :PoorCLISearch stats with one structured panel.
--
-- Summary block: RPC / Provider / Sandbox / MCP / Tools / Index / Services
-- Drilldown sections (<CR> to expand): Tools · MCP · Instructions · Services · Doctor

local rpc = require("poor-cli.rpc")

local M = {}

M.buf = nil
M.win = nil
M.ns = vim.api.nvim_create_namespace("poor-cli_diag")
M.cache = {}
M.expanded = {}
M.line_action = {}
M._inflight = {}

local GLYPH_OK = "✓"
local GLYPH_WARN = "⚠"
local GLYPH_ERR = "✗"
local GLYPH_INFO = "·"

local function hl_for(status)
    if status == "ok" then return GLYPH_OK, "DiagnosticOk" end
    if status == "warn" then return GLYPH_WARN, "DiagnosticWarn" end
    if status == "err" then return GLYPH_ERR, "DiagnosticError" end
    return GLYPH_INFO, "Comment"
end

local function clip(value, width)
    local text = tostring(value or ""):gsub("\n.*", "")
    if #text <= width then return text end
    return text:sub(1, math.max(1, width - 3)) .. "..."
end

local function notify(msg, level)
    require("poor-cli.notify").notify("[poor-cli] " .. msg, level)
end

local function fetch(method, key, params)
    if M._inflight[key] then return end
    M._inflight[key] = true
    rpc.request(method, params or {}, function(result, err)
        vim.schedule(function()
            M._inflight[key] = false
            if err then
                M.cache[key] = { error = rpc.format_error(err) }
            else
                M.cache[key] = result or {}
            end
            M.render()
        end)
    end)
end

-- ──────────────── Summary row builders ────────────────

local function row_rpc()
    local info = rpc.get_status and rpc.get_status() or {}
    local running = rpc.is_running and rpc.is_running() or false
    if running then
        return "ok", string.format("connected · pid %s", tostring(info.pid or "?"))
    end
    return "err", "not connected"
end

local function row_provider()
    local caps = rpc.get_capabilities and rpc.get_capabilities() or {}
    local pinfo = caps.providerInfo or {}
    if pinfo.name then
        return "ok", string.format("%s/%s", tostring(pinfo.name), tostring(pinfo.model or "?"))
    end
    return "warn", "not initialized"
end

local function row_mcp()
    local data = M.cache.mcp
    if not data then return "info", "loading…" end
    if data.error then return "err", data.error end
    local servers = data.servers or {}
    local healthy, unhealthy = 0, 0
    for _, s in ipairs(servers) do
        local err = s.lastError or s.error
        if err and err ~= "" then unhealthy = unhealthy + 1
        elseif s.status == "healthy" or s.connected == true then healthy = healthy + 1 end
    end
    if unhealthy > 0 then
        return "warn", string.format("%d/%d healthy · %d error", healthy, #servers, unhealthy)
    end
    if #servers == 0 then return "info", "no servers configured" end
    return "ok", string.format("%d/%d healthy", healthy, #servers)
end

local function row_sandbox()
    local data = M.cache.docker
    if not data then return "info", "loading…" end
    if data.error then return "warn", data.error end
    local enabled = data.enabled or data.dockerEnabled
    if enabled == false then return "info", "docker off · native sandbox" end
    if data.available == false then return "warn", "docker unavailable" end
    return "ok", string.format("docker · image %s", tostring(data.image or data.imageName or "?"))
end

local function row_tools()
    local data = M.cache.tools
    if not data then return "info", "loading…" end
    if data.error then return "err", data.error end
    local tools = data.tools or data
    local count = type(tools) == "table" and #tools or 0
    return "ok", string.format("%d registered", count)
end

local function row_instructions()
    local data = M.cache.instructions
    if not data then return "info", "loading…" end
    if data.error then return "warn", data.error end
    local sources = data.sources or {}
    return "ok", string.format("%d source%s", #sources, #sources == 1 and "" or "s")
end

-- ──────────────── Drill section renderers ────────────────

local DRILLS = {
    {
        id = "tools",
        title = "Tools",
        summary = function()
            local data = M.cache.tools
            if not data or data.error then return "" end
            local tools = data.tools or data
            return string.format("%d entries", type(tools) == "table" and #tools or 0)
        end,
        fetch = function() fetch("poor-cli/getTools", "tools") end,
        render = function(lines)
            local data = M.cache.tools or {}
            if data.error then
                table.insert(lines, "    error: " .. data.error); return
            end
            local tools = data.tools or data or {}
            if type(tools) ~= "table" or #tools == 0 then
                table.insert(lines, "    no tools registered"); return
            end
            for _, tool in ipairs(tools) do
                local name = type(tool) == "table" and (tool.name or "?") or tostring(tool)
                local desc = type(tool) == "table" and (tool.description or "") or ""
                local src  = type(tool) == "table" and (tool.source or tool.provider or "") or ""
                local src_tag = src ~= "" and (" [" .. src .. "]") or ""
                table.insert(lines, string.format("    %-28s%s  %s", clip(name, 28), src_tag, clip(desc, 80)))
            end
        end,
    },
    {
        id = "mcp",
        title = "MCP servers",
        summary = function()
            local data = M.cache.mcp
            if not data or data.error then return "" end
            return string.format("%d servers", #(data.servers or {}))
        end,
        fetch = function() fetch("poor-cli/mcpList", "mcp") end,
        render = function(lines)
            local data = M.cache.mcp or {}
            if data.error then
                table.insert(lines, "    error: " .. data.error); return
            end
            local servers = data.servers or {}
            if #servers == 0 then
                table.insert(lines, "    no servers configured"); return
            end
            for _, srv in ipairs(servers) do
                local err = srv.lastError or srv.error
                local status
                if err and err ~= "" then status = "error"
                elseif srv.status == "healthy" or srv.connected == true then status = "healthy"
                elseif srv.enabled == false then status = "disabled"
                else status = tostring(srv.status or "unknown") end
                table.insert(lines, string.format("    %-24s %-8s %-10s %d tools%s",
                    clip(srv.name or "?", 24),
                    clip(srv.transport or "stdio", 8),
                    status,
                    tonumber(srv.toolCount or srv.tools_count) or 0,
                    (err and err ~= "") and ("  error: " .. clip(err, 40)) or ""))
            end
        end,
    },
    {
        id = "instructions",
        title = "Context stack",
        summary = function()
            local data = M.cache.instructions
            if not data or data.error then return "" end
            return string.format("%d source%s", #(data.sources or {}),
                #(data.sources or {}) == 1 and "" or "s")
        end,
        fetch = function() fetch("poor-cli/getInstructionStack", "instructions") end,
        render = function(lines)
            local data = M.cache.instructions or {}
            if data.error then
                table.insert(lines, "    error: " .. data.error); return
            end
            local sources = data.sources or {}
            if #sources == 0 then
                table.insert(lines, "    no instruction sources"); return
            end
            for _, source in ipairs(sources) do
                local kind = source.kind or "?"
                local path = source.path or ""
                local enabled = source.enabled ~= false and "on" or "off"
                table.insert(lines, string.format("    [%-3s] %-14s %s", enabled, kind, clip(path, 80)))
            end
        end,
    },
    {
        id = "services",
        title = "Services",
        summary = function()
            local data = M.cache.services
            if not data or data.error then return "" end
            return string.format("%d background", #(data.services or {}))
        end,
        fetch = function() fetch("poor-cli/listServices", "services") end,
        render = function(lines)
            local data = M.cache.services or {}
            if data.error then
                table.insert(lines, "    error: " .. data.error); return
            end
            local services = data.services or {}
            if #services == 0 then
                table.insert(lines, "    no background services"); return
            end
            for _, svc in ipairs(services) do
                table.insert(lines, string.format("    %-16s %-10s pid=%s",
                    clip(svc.name or "?", 16),
                    tostring(svc.status or "?"),
                    tostring(svc.pid or "?")))
            end
        end,
    },
    {
        id = "doctor",
        title = "Doctor checks",
        summary = function()
            local data = M.cache.doctor
            if not data or data.error then return "" end
            local checks = data.checks or {}
            return string.format("%d check%s", #checks, #checks == 1 and "" or "s")
        end,
        fetch = function()
            if M._inflight.doctor then return end
            M._inflight.doctor = true
            if type(rpc.get_doctor_report) == "function" then
                local result, err = rpc.get_doctor_report(15000)
                M._inflight.doctor = false
                if err then M.cache.doctor = { error = rpc.format_error(err) }
                else M.cache.doctor = result or {} end
                M.render()
            else
                M._inflight.doctor = false
                M.cache.doctor = { error = "doctor RPC unavailable" }
                M.render()
            end
        end,
        render = function(lines)
            local data = M.cache.doctor or {}
            if data.error then
                table.insert(lines, "    error: " .. data.error); return
            end
            local checks = data.checks or {}
            if #checks == 0 then
                table.insert(lines, "    no checks reported"); return
            end
            for _, check in ipairs(checks) do
                local status = tostring(check.status or "unknown"):lower()
                local glyph = status == "ok" and GLYPH_OK
                    or (status == "warn" or status == "warning") and GLYPH_WARN
                    or (status == "error" or status == "fail" or status == "failed") and GLYPH_ERR
                    or GLYPH_INFO
                table.insert(lines, string.format("    %s %s — %s", glyph,
                    clip(check.title or "Check", 24), clip(check.message or "", 80)))
                if check.action and check.action ~= "" then
                    table.insert(lines, "        action: " .. tostring(check.action))
                end
            end
        end,
    },
}

function M.render()
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then return end
    local lines = { "# poor-cli diag", "" }
    M.line_action = {}
    local summary_rows = {
        { "RPC server",  row_rpc() },
        { "Provider",    row_provider() },
        { "Sandbox",     row_sandbox() },
        { "MCP",         row_mcp() },
        { "Tools",       row_tools() },
        { "Instructions",row_instructions() },
    }
    local badge_marks = {}
    for _, row in ipairs(summary_rows) do
        local label = row[1]
        local status = row[2]
        local detail = row[3] or ""
        local glyph, hl = hl_for(status)
        local line = string.format("  %s %-14s %s", glyph, label, detail)
        table.insert(lines, line)
        -- highlight the glyph
        badge_marks[#lines] = { col = 2, len = #glyph, hl = hl }
    end
    table.insert(lines, "")
    for _, drill in ipairs(DRILLS) do
        local arrow = M.expanded[drill.id] and "▾" or "▸"
        local summary = drill.summary() or ""
        table.insert(lines, string.format("%s %s %s",
            arrow, drill.title,
            summary ~= "" and ("  " .. summary) or ""))
        M.line_action[#lines] = { kind = "drill", id = drill.id }
        if M.expanded[drill.id] then
            drill.render(lines)
        end
    end
    table.insert(lines, "")
    table.insert(lines, "<CR> drill  r refresh  l log-open  s state-open  c copy-debug  q close")
    vim.bo[M.buf].modifiable = true
    vim.api.nvim_buf_clear_namespace(M.buf, M.ns, 0, -1)
    vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, lines)
    for line, mark in pairs(badge_marks) do
        pcall(vim.api.nvim_buf_set_extmark, M.buf, M.ns, line - 1, mark.col, {
            end_col = mark.col + mark.len,
            hl_group = mark.hl,
        })
    end
    vim.bo[M.buf].modifiable = false
end

function M.refresh()
    -- kick background fetches for summary rows
    fetch("poor-cli/mcpList", "mcp")
    fetch("poor-cli/dockerSandboxStatus", "docker")
    fetch("poor-cli/getTools", "tools")
    fetch("poor-cli/getInstructionStack", "instructions")
    fetch("poor-cli/listServices", "services")
    M.render()
end

function M.toggle_drill()
    local line = vim.api.nvim_win_get_cursor(M.win or 0)[1]
    local action = M.line_action[line]
    if not (action and action.kind == "drill") then return end
    local was = M.expanded[action.id]
    M.expanded[action.id] = not was
    if not was then
        -- fetch on first expand if we don't have data yet
        for _, drill in ipairs(DRILLS) do
            if drill.id == action.id and not M.cache[action.id] and drill.fetch then
                drill.fetch()
                break
            end
        end
    end
    M.render()
end

function M.close()
    if M.win and vim.api.nvim_win_is_valid(M.win) then vim.api.nvim_win_close(M.win, true) end
    M.win = nil
end

function M.open(opts)
    opts = opts or {}
    if opts.expand then M.expanded[opts.expand] = true end
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_set_current_win(M.win)
        M.refresh()
        return M.buf
    end
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then
        M.buf = vim.api.nvim_create_buf(false, true)
        vim.bo[M.buf].buftype = "nofile"
        vim.bo[M.buf].bufhidden = "hide"
        vim.bo[M.buf].swapfile = false
        vim.bo[M.buf].filetype = "markdown"
        vim.api.nvim_buf_set_name(M.buf, "[poor-cli diag]")
    end
    local float_win = require("poor-cli.float_win")
    M.win = float_win.open(M.buf, {
        width = math.min(100, vim.o.columns - 4),
        height = math.max(24, math.floor(vim.o.lines * 0.8)),
        position = "center",
        title = " poor-cli diag ",
        close_keys = {},
        wrap = false,
    })
    vim.keymap.set("n", "q", M.close, { buffer = M.buf, nowait = true })
    vim.keymap.set("n", "<Esc>", M.close, { buffer = M.buf, nowait = true })
    vim.keymap.set("n", "r", M.refresh, { buffer = M.buf, nowait = true })
    vim.keymap.set("n", "<CR>", M.toggle_drill, { buffer = M.buf, nowait = true })
    vim.keymap.set("n", "l", function() vim.cmd("edit " .. vim.fn.fnameescape(rpc.get_log_path())) end, { buffer = M.buf, nowait = true })
    vim.keymap.set("n", "s", function() vim.cmd("edit " .. vim.fn.fnameescape(require("poor-cli.config").get_state_dir())) end, { buffer = M.buf, nowait = true })
    vim.keymap.set("n", "c", function()
        local report = rpc.build_debug_report and rpc.build_debug_report({}) or ""
        pcall(vim.fn.setreg, "+", tostring(report))
        notify("debug report copied to clipboard", vim.log.levels.INFO)
    end, { buffer = M.buf, nowait = true })
    -- pre-expand doctor drill if asked (e.g. from :PoorCLIDiag doctor)
    if opts.expand and M.expanded[opts.expand] then
        for _, drill in ipairs(DRILLS) do
            if drill.id == opts.expand and drill.fetch then drill.fetch(); break end
        end
    end
    M.refresh()
    return M.buf
end

return M
