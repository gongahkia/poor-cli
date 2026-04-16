local rpc = require("poor-cli.rpc")
local policy_summary = require("poor-cli.policy_summary")

local M = {
    ns = vim.api.nvim_create_namespace("poor-cli-trust-center"),
    buffers = {},
    audit_limit = 8,
    custom_sections = {},
}

local action_methods = {
    toggle_sandbox = "sandbox/toggle",
    view_permissions = "permissions/list",
    rotate_audit = "audit/rotateNow",
    export_audit = "audit/exportRange",
}

local function t(v) return type(v) == "table" and v or {} end
local function s(v, fallback) if v == nil or v == "" then return fallback or "" end return tostring(v) end
local function b(v) return v and "yes" or "no" end

local function wipe_named_buffer(name)
    local existing = vim.fn.bufnr(name)
    if existing == -1 then return end
    for _, win in ipairs(vim.fn.win_findbuf(existing)) do
        pcall(vim.api.nvim_win_set_buf, win, vim.api.nvim_create_buf(false, true))
    end
    pcall(vim.api.nvim_buf_delete, existing, { force = true })
end

local function scratch_buf()
    wipe_named_buffer("[poor-cli trust center]")
    local buf = vim.api.nvim_create_buf(false, true)
    vim.bo[buf].buftype = "nofile"
    vim.bo[buf].bufhidden = "wipe"
    vim.bo[buf].swapfile = false
    vim.bo[buf].modifiable = true
    vim.bo[buf].filetype = "poor-clitrust"
    vim.api.nvim_buf_set_name(buf, "[poor-cli trust center]")
    return buf
end

local function ensure_window(buf)
    if vim.api.nvim_get_current_buf() ~= buf then
        local float_win = require("poor-cli.float_win")
        float_win.open(buf, {
            width = 0.8,
            height = 0.8,
            position = "center",
            title = " poor-cli trust center ",
            close_keys = { "q", "<Esc>" },
        })
    end
end

local function add_action(state, line, id, label, params)
    state.actions[line] = { id = id, label = label, params = params or {} }
end

local function add_line(lines, text)
    table.insert(lines, text)
    return #lines
end

local function add_section(lines, title)
    table.insert(lines, "")
    table.insert(lines, "## " .. title)
end

local function flatten_rules(rules)
    return policy_summary.flatten_rules(rules)
end

local function render_permission_rules(lines, rules)
    local flat = flatten_rules(rules)
    add_section(lines, "Permission rule detail")
    if #flat == 0 then
        add_line(lines, "  no permission rules")
        return
    end
    for _, rule in ipairs(flat) do
        add_line(lines, string.format(
            "  %s | %s | %s | %s",
            s(rule.behavior or rule.outcome, "prompt"),
            s(rule.scope or rule.source, "session"),
            s(rule.toolName or rule.name, "*"),
            s(rule.ruleContent or rule.source, "")
        ))
    end
end

local function event_label(event)
    local op = event.operation or event.event_type or event.type or event.name or "event"
    local target = event.target and tostring(event.target) or ""
    if target ~= "" then return tostring(op) .. " -> " .. target end
    return tostring(op)
end

local function render_event_detail(lines, event)
    add_section(lines, "Audit event detail")
    if type(event) ~= "table" then
        add_line(lines, "  no event selected")
        return
    end
    for _, key in ipairs({ "event_id", "event_type", "severity", "timestamp", "user", "operation", "target", "success", "error_message" }) do
        if event[key] ~= nil then add_line(lines, "  " .. key .. ": " .. tostring(event[key])) end
    end
    if event.details ~= nil then add_line(lines, "  details: " .. tostring(event.details)) end
end

local function custom_lines(section, status)
    if type(section) == "function" then return section(status) end
    if type(section) == "table" and type(section.render) == "function" then return section.render(status) end
    return nil
end

function M.build_lines(status, state)
    status = t(status)
    state = state or { actions = {} }
    state.actions = {}
    local lines = { "# poor-cli trust center" }
    local rules = status.permissionRules or t(status.policy).rules or {}
    local counts = status.policySummary or policy_summary.counts(rules)
    add_line(lines, "Policy summary: " .. policy_summary.summary_line(counts))

    add_section(lines, "Provider")
    add_line(lines, "  provider: " .. s(status.providerName or status.provider, "unknown"))
    add_line(lines, "  model: " .. s(status.providerModel or status.model, "unknown"))
    add_line(lines, "  routing: " .. s(status.routingMode, "manual"))

    add_section(lines, "Sandbox preset")
    add_line(lines, "  preset: " .. s(status.sandboxPreset, "workspace-write"))
    add_action(state, add_line(lines, "  action:"), "toggle_sandbox", "[Toggle sandbox]")

    add_section(lines, "Permission mode")
    add_line(lines, "  mode: " .. s(status.permissionMode, "prompt"))

    add_section(lines, "Permission rules count")
    add_line(lines, "  rules: " .. tostring(status.permissionRulesCount or counts.total or 0))
    add_action(state, add_line(lines, "  action:"), "view_permissions", "[View permission rules]")

    add_section(lines, "Rollback")
    add_line(lines, "  checkpointing: " .. b(status.checkpointing))
    add_line(lines, "  retained: " .. s(status.rollbackRetained or status.checkpointsRetained, "unknown"))

    add_section(lines, "Audit log")
    add_line(lines, "  enabled: " .. b(status.auditEnabled))
    add_line(lines, "  path: " .. s(status.auditPath, ""))
    add_line(lines, "  live rows: " .. tostring(status.auditRowCount or 0))
    add_action(state, add_line(lines, "  action:"), "rotate_audit", "[Rotate audit log]")
    add_action(state, add_line(lines, "  action:"), "export_audit", "[Export audit]")
    add_line(lines, "  recent events:")
    local events = t(status.auditEvents)
    if #events == 0 then
        add_line(lines, "    none")
    else
        for i, event in ipairs(events) do
            local line = add_line(lines, string.format("    %s %s", s(event.timestamp, ""), event_label(event)))
            add_action(state, line, "event_detail", "[Jump detail]", { index = i })
        end
    end

    add_section(lines, "Privacy")
    add_line(lines, "  posture: " .. s(status.privacyPosture, "unknown"))
    add_line(lines, "  data leaves machine: " .. b(status.dataLeavesMachine))

    add_section(lines, "Memory")
    local sources = status.memorySources or status.agentsSources or {}
    if type(sources) == "table" and #sources > 0 then
        for _, source in ipairs(sources) do add_line(lines, "  " .. s(source)) end
    else
        add_line(lines, "  AGENTS.md sources: none")
    end

    if state.detail == "permissions" then render_permission_rules(lines, state.permission_rules or rules) end
    if state.detail == "event" then render_event_detail(lines, state.detail_event) end

    for _, section in ipairs(M.custom_sections) do
        local rendered = custom_lines(section, status)
        if type(rendered) == "table" and #rendered > 0 then
            local title = type(section) == "table" and section.title or "Custom"
            add_section(lines, title)
            for _, line in ipairs(rendered) do add_line(lines, tostring(line)) end
        end
    end

    return lines
end

function M.redraw(buf, status)
    local state = M.buffers[buf]
    if not state then return end
    status = status or state.status or {}
    state.status = status
    local cursor = { 1, 0 }
    local win = vim.fn.bufwinid(buf)
    if win ~= -1 then cursor = vim.api.nvim_win_get_cursor(win) end
    local lines = M.build_lines(status, state)
    vim.bo[buf].modifiable = true
    vim.api.nvim_buf_clear_namespace(buf, M.ns, 0, -1)
    vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
    for line, action in pairs(state.actions) do
        vim.api.nvim_buf_set_extmark(buf, M.ns, line - 1, 0, {
            virt_text = { { " " .. action.label, "PoorCLITrustCenterAction" } },
            virt_text_pos = "eol",
        })
    end
    vim.bo[buf].modifiable = false
    if win ~= -1 then
        cursor[1] = math.min(cursor[1], #lines)
        pcall(vim.api.nvim_win_set_cursor, win, cursor)
    end
end

local function normalize_trust_view(payload)
    local session = t(payload.session)
    local trust = t(payload.trust)
    local provider = t(payload.provider)
    local active = t(provider.active)
    local policy = t(trust.policy)
    local audit = t(trust.audit)
    local recovery = t(payload.recovery)
    local last_mutation = t(recovery.lastMutation)
    local security = t(trust.security)
    return {
        providerName = active.name,
        providerModel = active.model,
        routingMode = session.routingMode,
        permissionMode = session.permissionMode,
        sandboxPreset = trust.sandboxPreset,
        checkpointing = trust.checkpointing,
        rollbackRetained = last_mutation.checkpointId or "",
        auditEnabled = audit.enabled,
        auditPath = audit.path,
        privacyPosture = provider.privacyPosture,
        dataLeavesMachine = provider.privacyPosture ~= "local",
        memorySources = security.trustedRoots or {},
        policy = policy,
        permissionRules = payload.permissionRules or {},
        auditEvents = payload.auditEvents or {},
        auditRowCount = payload.auditRowCount or 0,
    }
end

function M.fetch_status(callback)
    rpc.request("poor-cli/trustStatus", { auditLimit = M.audit_limit }, function(result, err)
        if err then
            rpc.request("poor-cli/getTrustView", {}, function(fallback, fallback_err)
                if fallback_err then callback(nil, fallback_err); return end
                callback(normalize_trust_view(fallback or {}), nil)
            end)
            return
        end
        callback(result or {}, nil)
    end)
end

function M.refresh(buf)
    M.fetch_status(function(status, err)
        if err then
            require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
            return
        end
        M.redraw(buf, status)
    end)
end

function M.dispatch(buf, action)
    local state = M.buffers[buf]
    if not state then return end
    if action.id == "event_detail" then
        state.detail = "event"
        state.detail_event = t(state.status.auditEvents)[action.params.index]
        M.redraw(buf)
        local win = vim.fn.bufwinid(buf)
        if win ~= -1 then pcall(vim.api.nvim_win_set_cursor, win, { vim.api.nvim_buf_line_count(buf), 0 }) end
        return
    end
    local method = action_methods[action.id]
    if not method then return end
    rpc.request(method, action.params or {}, function(result, err)
        if err then
            require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
            return
        end
        if action.id == "view_permissions" then
            state.detail = "permissions"
            state.permission_rules = t(result).rules or result or {}
            M.refresh(buf)
            return
        end
        if action.id == "export_audit" and t(result).path then
            require("poor-cli.notify").notify("[poor-cli] audit exported: " .. tostring(result.path), vim.log.levels.INFO)
        end
        M.refresh(buf)
    end)
end

function M.invoke_action(buf)
    buf = buf or vim.api.nvim_get_current_buf()
    local state = M.buffers[buf]
    if not state then return false end
    local line = vim.api.nvim_win_get_cursor(0)[1]
    local action = state.actions[line]
    if not action then return false end
    M.dispatch(buf, action)
    return true
end

function M.open(opts)
    opts = opts or {}
    M.audit_limit = opts.audit_limit or M.audit_limit
    local buf = opts.buf or scratch_buf()
    M.buffers[buf] = { actions = {}, status = {}, detail = nil }
    ensure_window(buf)
    vim.keymap.set("n", "<CR>", function() M.invoke_action(buf) end, { buffer = buf, silent = true, nowait = true })
    vim.keymap.set("n", "r", function() M.refresh(buf) end, { buffer = buf, silent = true, nowait = true })
    vim.keymap.set("n", "q", ":close<CR>", { buffer = buf, silent = true, nowait = true })
    M.refresh(buf)
    return buf
end

function M.setup(opts)
    if type(opts) == "table" and type(opts.sections) == "table" then
        M.custom_sections = opts.sections
    end
end

M._action_methods = action_methods

return M
