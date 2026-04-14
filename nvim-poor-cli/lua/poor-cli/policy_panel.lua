local rpc = require("poor-cli.rpc")
local policy_summary = require("poor-cli.policy_summary")

local M = {
    ns = vim.api.nvim_create_namespace("poor-cli-policy-panel"),
    buffers = {},
    width = 60,
}

local widths = { name = 22, scope = 12, outcome = 8 }
local outcome_col = widths.name + 1 + widths.scope + 1

local function s(v, fallback)
    if v == nil or v == "" then return fallback or "" end
    return tostring(v)
end

local function clip(v, width)
    local text = s(v)
    if #text <= width then return text end
    if width <= 1 then return text:sub(1, width) end
    return text:sub(1, width - 1) .. "~"
end

local function outcome(raw)
    local value = tostring(raw or ""):lower()
    if value == "ask" then return "prompt" end
    if value == "allow" or value == "deny" or value == "prompt" then return value end
    return "prompt"
end

local function outcome_hl(value)
    if value == "allow" then return "PoorCLIPolicyAllow" end
    if value == "deny" then return "PoorCLIPolicyDeny" end
    return "PoorCLIPolicyPrompt"
end

local function row_line(rule)
    return string.format(
        "%-" .. widths.name .. "s %-" .. widths.scope .. "s %-" .. widths.outcome .. "s %s",
        clip(rule.name, widths.name),
        clip(rule.scope, widths.scope),
        clip(rule.outcome, widths.outcome),
        s(rule.source, "")
    )
end

local function normalize_payload(payload)
    local raw = type(payload) == "table" and (payload.rules or payload) or {}
    raw = policy_summary.flatten_rules(raw)
    local out = {}
    for index, rule in ipairs(raw) do
        local normalized = {
            index = tonumber(rule.index) or index,
            name = s(rule.name or rule.toolName or "*", "*"),
            scope = s(rule.scope, "global"),
            outcome = outcome(rule.outcome or rule.behavior),
            source = s(rule.source, rule.scope or ""),
            file = s(rule.file, ""),
            line = tonumber(rule.line) or 0,
            ruleContent = s(rule.ruleContent, ""),
        }
        table.insert(out, normalized)
    end
    return out
end

local function define_highlights()
    pcall(vim.api.nvim_set_hl, 0, "PoorCLIPolicyAllow", { link = "DiagnosticOk", default = true })
    pcall(vim.api.nvim_set_hl, 0, "PoorCLIPolicyDeny", { link = "DiagnosticError", default = true })
    pcall(vim.api.nvim_set_hl, 0, "PoorCLIPolicyPrompt", { link = "DiagnosticWarn", default = true })
end

local function wipe_named_buffer(name)
    local existing = vim.fn.bufnr(name)
    if existing == -1 then return end
    for _, win in ipairs(vim.fn.win_findbuf(existing)) do
        pcall(vim.api.nvim_win_set_buf, win, vim.api.nvim_create_buf(false, true))
    end
    pcall(vim.api.nvim_buf_delete, existing, { force = true })
end

local function scratch_buf()
    wipe_named_buffer("[poor-cli policy]")
    local buf = vim.api.nvim_create_buf(false, true)
    vim.bo[buf].buftype = "nofile"
    vim.bo[buf].bufhidden = "hide"
    vim.bo[buf].swapfile = false
    vim.bo[buf].modifiable = true
    vim.bo[buf].filetype = "poor-clipolicy"
    vim.api.nvim_buf_set_name(buf, "[poor-cli policy]")
    return buf
end

local function ensure_window(buf)
    if vim.api.nvim_get_current_buf() == buf then return end
    vim.cmd("botright " .. M.width .. "vsplit")
    vim.api.nvim_win_set_buf(0, buf)
end

local function source_key(file)
    if file == nil or file == "" then return "" end
    return vim.fn.fnamemodify(file, ":p")
end

function M.redraw(buf)
    local state = M.buffers[buf]
    if not state or not vim.api.nvim_buf_is_valid(buf) then return end
    state.rows = {}
    state.source_files = {}
    local lines = {
        "# poor-cli policy",
        "",
        row_line({ name = "name", scope = "scope", outcome = "outcome", source = "source" }),
        row_line({ name = string.rep("-", 4), scope = string.rep("-", 5), outcome = string.rep("-", 7), source = string.rep("-", 6) }),
    }
    if #state.rules == 0 then
        table.insert(lines, "no permission rules")
    else
        for _, rule in ipairs(state.rules) do
            table.insert(lines, row_line(rule))
            state.rows[#lines] = rule
            local key = source_key(rule.file)
            if key ~= "" then state.source_files[key] = true end
        end
    end
    vim.bo[buf].modifiable = true
    vim.api.nvim_buf_clear_namespace(buf, M.ns, 0, -1)
    vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
    for line, rule in pairs(state.rows) do
        vim.api.nvim_buf_set_extmark(buf, M.ns, line - 1, outcome_col, {
            end_col = outcome_col + #rule.outcome,
            hl_group = outcome_hl(rule.outcome),
        })
    end
    vim.bo[buf].modifiable = false
end

local function request_rules(method, callback)
    if method == "policy.list" and type(rpc.policy_list) == "function" then
        return rpc.policy_list(callback)
    end
    if method == "policy.reload" and type(rpc.policy_reload) == "function" then
        return rpc.policy_reload(callback)
    end
    rpc.request(method, {}, function(result, err)
        callback(result, err)
    end)
end

function M.reload(buf, method)
    local state = M.buffers[buf]
    if not state or not vim.api.nvim_buf_is_valid(buf) then return end
    request_rules(method or "policy.reload", function(result, err)
        if err then
            require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
            return
        end
        state.rules = normalize_payload(result)
        M.redraw(buf)
    end)
end

function M.jump(buf)
    buf = buf or vim.api.nvim_get_current_buf()
    local state = M.buffers[buf]
    if not state then return false end
    local row = state.rows[vim.api.nvim_win_get_cursor(0)[1]]
    if not row then return false end
    local request_edit = type(rpc.policy_edit) == "function" and rpc.policy_edit or function(rule, cb)
        return rpc.request("policy.edit", rule, cb)
    end
    request_edit({ index = row.index, rule = row }, function(result, err)
        if err then
            require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
            return
        end
        local target = type(result) == "table" and result or row
        local file = s(target.file or row.file, "")
        if file == "" then
            require("poor-cli.notify").notify("[poor-cli] rule has no source file", vim.log.levels.WARN)
            return
        end
        local line = tonumber(target.line or row.line) or 1
        vim.cmd("edit " .. vim.fn.fnameescape(file))
        pcall(vim.api.nvim_win_set_cursor, 0, { math.max(line, 1), 0 })
    end)
    return true
end

local function install_autocmd(buf)
    local state = M.buffers[buf]
    if not state then return end
    state.augroup = vim.api.nvim_create_augroup("poor-cli-policy-panel-" .. buf, { clear = true })
    vim.api.nvim_create_autocmd("BufWritePost", {
        group = state.augroup,
        pattern = "*",
        callback = function(args)
            if state.source_files[source_key(args.file)] then M.reload(buf) end
        end,
    })
end

function M.open(opts)
    opts = opts or {}
    define_highlights()
    local buf = opts.buf or scratch_buf()
    M.buffers[buf] = { rules = {}, rows = {}, source_files = {} }
    ensure_window(buf)
    vim.keymap.set("n", "<CR>", function() M.jump(buf) end, { buffer = buf, silent = true, nowait = true })
    vim.keymap.set("n", "gf", function() M.jump(buf) end, { buffer = buf, silent = true, nowait = true })
    vim.keymap.set("n", "R", function() M.reload(buf) end, { buffer = buf, silent = true, nowait = true })
    vim.keymap.set("n", "r", function() M.reload(buf) end, { buffer = buf, silent = true, nowait = true })
    vim.keymap.set("n", "q", ":close<CR>", { buffer = buf, silent = true, nowait = true })
    install_autocmd(buf)
    M.reload(buf, "policy.list")
    return buf
end

return M
