-- poor-cli/trust_center.lua
-- Collapsible-tree trust center. Absorbs the legacy policy panel, trust-show,
-- and permissions-show screens. Each section is a node that can be expanded
-- via <CR>; actions fire via single-letter keys shown in the footer legend
-- when a section is active.

local rpc = require("poor-cli.rpc")
local policy_summary = require("poor-cli.policy_summary")

local M = {
    ns = vim.api.nvim_create_namespace("poor-cli-trust-center"),
    buffers = {},
    audit_limit = 20,
    custom_sections = {},
}

local SECTION_ORDER = { "sandbox", "permission", "audit", "privacy", "memory", "rollback" }

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

local function outcome_hl(outcome)
    if outcome == "allow" then return "PoorCLIPolicyAllow" end
    if outcome == "deny"  then return "PoorCLIPolicyDeny" end
    return "PoorCLIPolicyPrompt"
end

local function normalize_outcome(raw)
    local v = tostring(raw or ""):lower()
    if v == "ask" then return "prompt" end
    if v == "allow" or v == "deny" or v == "prompt" then return v end
    return "prompt"
end

local function define_highlights()
    pcall(vim.api.nvim_set_hl, 0, "PoorCLIPolicyAllow", { link = "DiagnosticOk", default = true })
    pcall(vim.api.nvim_set_hl, 0, "PoorCLIPolicyDeny", { link = "DiagnosticError", default = true })
    pcall(vim.api.nvim_set_hl, 0, "PoorCLIPolicyPrompt", { link = "DiagnosticWarn", default = true })
    pcall(vim.api.nvim_set_hl, 0, "PoorCLITrustCenterAction", { link = "Title", default = true })
    pcall(vim.api.nvim_set_hl, 0, "PoorCLITrustCenterSection", { link = "Title", default = true })
end

-- ───────────────── section renderers ─────────────────

local function section_sandbox(status, state, lines, acc)
    local id = "sandbox"
    local expanded = state.expanded[id] ~= false -- default expanded
    local arrow = expanded and "▾" or "▸"
    table.insert(lines, string.format("%s sandbox           %s", arrow, s(status.sandboxPreset, "workspace-write")))
    acc.section_hl[#lines] = true
    acc.section_line[#lines] = id
    if expanded then
        table.insert(lines, "    preset: " .. s(status.sandboxPreset, "workspace-write"))
        table.insert(lines, "    [t] cycle preset")
        acc.actions[#lines] = { id = "toggle_sandbox", letter = "t" }
    end
end

local function section_permission(status, state, lines, acc)
    local rules = status.permissionRules or t(status.policy).rules or {}
    local flat = policy_summary.flatten_rules(rules)
    local counts = status.policySummary or policy_summary.counts(rules)
    local id = "permission"
    local expanded = state.expanded[id] ~= false
    local arrow = expanded and "▾" or "▸"
    local summary = string.format("%s · %d allow · %d deny · %d prompt",
        s(status.permissionMode, "prompt"),
        counts.allow or 0, counts.deny or 0, counts.prompt or 0)
    table.insert(lines, string.format("%s permission        %s", arrow, summary))
    acc.section_hl[#lines] = true
    acc.section_line[#lines] = id
    if expanded then
        local rules_expanded = state.expanded["permission.rules"] == true
        local r_arrow = rules_expanded and "▾" or "▸"
        table.insert(lines, string.format("    %s rules (%d)", r_arrow, counts.total or 0))
        acc.section_line[#lines] = "permission.rules"
        if rules_expanded then
            if #flat == 0 then
                table.insert(lines, "      no permission rules")
            else
                for _, rule in ipairs(flat) do
                    local outcome = normalize_outcome(rule.outcome or rule.behavior)
                    local name = s(rule.toolName or rule.name, "*")
                    local scope = s(rule.scope, "global")
                    local source = s(rule.file or rule.source, "")
                    local line = string.format("      %-28s %-10s %-8s %s", name, scope, outcome, source)
                    table.insert(lines, line)
                    -- outcome column starts at col 28 + 1 + 10 + 1 + 6 (prefix) = 46; compute dynamically
                    local col = #"      " + 28 + 1 + 10 + 1
                    acc.badges[#lines] = { col = col, len = #outcome, hl = outcome_hl(outcome) }
                    acc.rule_rows[#lines] = {
                        file = s(rule.file, ""),
                        line = tonumber(rule.line) or 1,
                        index = tonumber(rule.index) or 0,
                        rule = rule,
                    }
                end
            end
        end
        table.insert(lines, "    [a] add  [e] edit  [x] delete  [m] cycle mode")
        acc.actions[#lines] = { id = "permission.menu", letter = nil }
    end
end

local function section_audit(status, state, lines, acc)
    local id = "audit"
    local expanded = state.expanded[id] == true
    local arrow = expanded and "▾" or "▸"
    local enabled_str = b(status.auditEnabled)
    local row_count = tostring(status.auditRowCount or 0)
    table.insert(lines, string.format("%s audit             %s · %s rows · %s",
        arrow, enabled_str, row_count, s(status.auditPath, "")))
    acc.section_hl[#lines] = true
    acc.section_line[#lines] = id
    if expanded then
        table.insert(lines, "    enabled: " .. enabled_str)
        table.insert(lines, "    path: " .. s(status.auditPath, ""))
        table.insert(lines, "    rows: " .. row_count)
        table.insert(lines, "    [o] rotate  [e] export")
        acc.actions[#lines] = { id = "audit.menu" }
        local events = t(status.auditEvents)
        if #events > 0 then
            table.insert(lines, "    recent:")
            for i, event in ipairs(events) do
                if i > M.audit_limit then break end
                local op = event.operation or event.event_type or event.type or event.name or "event"
                local target = event.target and (" -> " .. tostring(event.target)) or ""
                table.insert(lines, string.format("      %s %s%s",
                    s(event.timestamp, ""), tostring(op), target))
                acc.actions[#lines] = { id = "event_detail", params = { index = i } }
            end
        end
    end
end

local function section_privacy(status, state, lines, acc)
    local id = "privacy"
    local expanded = state.expanded[id] == true
    local arrow = expanded and "▾" or "▸"
    table.insert(lines, string.format("%s privacy           posture=%s · data leaves machine=%s",
        arrow, s(status.privacyPosture, "unknown"), b(status.dataLeavesMachine)))
    acc.section_hl[#lines] = true
    acc.section_line[#lines] = id
end

local function section_memory(status, state, lines, acc)
    local id = "memory"
    local expanded = state.expanded[id] == true
    local arrow = expanded and "▾" or "▸"
    local sources = status.memorySources or status.agentsSources or {}
    local count = type(sources) == "table" and #sources or 0
    table.insert(lines, string.format("%s memory            %d AGENTS.md source%s",
        arrow, count, count == 1 and "" or "s"))
    acc.section_hl[#lines] = true
    acc.section_line[#lines] = id
    if expanded and count > 0 then
        for _, source in ipairs(sources) do
            table.insert(lines, "    " .. s(source))
        end
    end
end

local function section_rollback(status, state, lines, acc)
    local id = "rollback"
    local expanded = state.expanded[id] == true
    local arrow = expanded and "▾" or "▸"
    table.insert(lines, string.format("%s rollback          checkpointing=%s · retained=%s",
        arrow, b(status.checkpointing),
        s(status.rollbackRetained or status.checkpointsRetained, "unknown")))
    acc.section_hl[#lines] = true
    acc.section_line[#lines] = id
end

local SECTION_RENDERERS = {
    sandbox    = section_sandbox,
    permission = section_permission,
    audit      = section_audit,
    privacy    = section_privacy,
    memory     = section_memory,
    rollback   = section_rollback,
}

function M.build_lines(status, state)
    status = t(status)
    state = state or { expanded = {}, actions = {}, section_line = {}, section_hl = {}, badges = {}, rule_rows = {} }
    state.expanded = state.expanded or {}
    state.actions = {}
    state.section_line = {}
    state.section_hl = {}
    state.badges = {}
    state.rule_rows = {}

    local rules = status.permissionRules or t(status.policy).rules or {}
    local counts = status.policySummary or policy_summary.counts(rules)
    local lines = {
        "# poor-cli trust",
        string.format("provider %s/%s · %s · %s · %d rules (allow=%d deny=%d prompt=%d)",
            s(status.providerName or status.provider, "unknown"),
            s(status.providerModel or status.model, "unknown"),
            s(status.sandboxPreset, "workspace-write"),
            s(status.permissionMode, "prompt"),
            counts.total or 0,
            counts.allow or 0, counts.deny or 0, counts.prompt or 0),
        "",
    }

    for _, id in ipairs(SECTION_ORDER) do
        SECTION_RENDERERS[id](status, state, lines, state)
        table.insert(lines, "")
    end

    for _, section in ipairs(M.custom_sections) do
        local rendered
        if type(section) == "function" then
            rendered = section(status)
        elseif type(section) == "table" and type(section.render) == "function" then
            rendered = section.render(status)
        end
        if type(rendered) == "table" and #rendered > 0 then
            table.insert(lines, "## " .. (type(section) == "table" and section.title or "Custom"))
            for _, line in ipairs(rendered) do table.insert(lines, tostring(line)) end
            table.insert(lines, "")
        end
    end

    table.insert(lines, "<CR> expand/collapse section  letter keys for actions  r refresh  q close")
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
    -- section header highlights
    for line, _ in pairs(state.section_hl) do
        vim.api.nvim_buf_set_extmark(buf, M.ns, line - 1, 0, {
            end_col = #(lines[line] or ""),
            hl_group = "PoorCLITrustCenterSection",
        })
    end
    -- outcome badges (inside expanded permission rules)
    for line, badge in pairs(state.badges) do
        pcall(vim.api.nvim_buf_set_extmark, buf, M.ns, line - 1, badge.col, {
            end_col = badge.col + badge.len,
            hl_group = badge.hl,
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

-- ───────────────── dispatch ─────────────────

local function toggle_section_under_cursor(buf)
    local state = M.buffers[buf]
    if not state then return false end
    local line = vim.api.nvim_win_get_cursor(0)[1]
    local section_id = state.section_line[line]
    if not section_id then return false end
    state.expanded[section_id] = not state.expanded[section_id]
    M.redraw(buf)
    return true
end

function M.dispatch(buf, action)
    local state = M.buffers[buf]
    if not state then return end
    if action.id == "event_detail" then
        state.detail_event = t(state.status.auditEvents)[action.params.index]
        if state.detail_event then
            local float_win = require("poor-cli.float_win")
            float_win.open_lines(vim.split(vim.inspect(state.detail_event), "\n", { plain = true }), {
                filetype = "lua",
                name = "[poor-cli audit event]",
                title = " audit event ",
                width = 0.6, height = 0.5, position = "center",
            })
        end
        return
    end
    local method = action_methods[action.id]
    if not method then return end
    rpc.request(method, action.params or {}, function(result, err)
        if err then
            require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
            return
        end
        if action.id == "export_audit" and t(result).path then
            require("poor-cli.notify").notify("[poor-cli] audit exported: " .. tostring(result.path), vim.log.levels.INFO)
        end
        M.refresh(buf)
    end)
end

function M.jump_to_rule(buf)
    local state = M.buffers[buf]
    if not state then return false end
    local line = vim.api.nvim_win_get_cursor(0)[1]
    local row = state.rule_rows[line]
    if not row or not row.file or row.file == "" then return false end
    vim.cmd("edit " .. vim.fn.fnameescape(row.file))
    pcall(vim.api.nvim_win_set_cursor, 0, { math.max(row.line, 1), 0 })
    return true
end

-- letter-key dispatchers: map by active section
local function on_letter(buf, letter)
    local state = M.buffers[buf]
    if not state then return end
    local line = vim.api.nvim_win_get_cursor(0)[1]
    -- find which section the cursor is inside by walking upward
    local section = nil
    for i = line, 1, -1 do
        if state.section_line[i] and SECTION_RENDERERS[state.section_line[i]] then
            section = state.section_line[i]; break
        end
    end
    if section == "sandbox" and letter == "t" then
        M.dispatch(buf, { id = "toggle_sandbox" }); return
    end
    if section == "audit" then
        if letter == "o" then M.dispatch(buf, { id = "rotate_audit" }); return end
        if letter == "e" then M.dispatch(buf, { id = "export_audit" }); return end
    end
end

function M.open(opts)
    opts = opts or {}
    define_highlights()
    M.audit_limit = opts.audit_limit or M.audit_limit
    local buf = opts.buf or scratch_buf()
    M.buffers[buf] = {
        expanded = opts.expanded or { sandbox = true, permission = true },
        actions = {},
        status = {},
        section_line = {},
        section_hl = {},
        badges = {},
        rule_rows = {},
    }
    if opts.expand then M.buffers[buf].expanded[opts.expand] = true end
    ensure_window(buf)
    vim.keymap.set("n", "<CR>", function()
        if not toggle_section_under_cursor(buf) then
            M.jump_to_rule(buf)
        end
    end, { buffer = buf, silent = true, nowait = true })
    vim.keymap.set("n", "gf", function() M.jump_to_rule(buf) end, { buffer = buf, silent = true, nowait = true })
    vim.keymap.set("n", "t", function() on_letter(buf, "t") end, { buffer = buf, silent = true, nowait = true })
    vim.keymap.set("n", "o", function() on_letter(buf, "o") end, { buffer = buf, silent = true, nowait = true })
    vim.keymap.set("n", "e", function() on_letter(buf, "e") end, { buffer = buf, silent = true, nowait = true })
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
