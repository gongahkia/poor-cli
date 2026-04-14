-- poor-cli/diagnostics.lua
-- Inline diagnostics extracted from assistant file:line suggestions.

local config = require("poor-cli.config")

local M = {}

M.ns = vim.api.nvim_create_namespace("poor-cli-diagnostics")

local function emit_suggestions_changed()
    pcall(vim.api.nvim_exec_autocmds, "User", {
        pattern = "PoorCLISuggestionsChanged",
    })
end

local function normalize_path(raw_path)
    if not raw_path or raw_path == "" then
        return nil
    end

    local cleaned = raw_path:gsub("^[`'\"]", ""):gsub("[`'\",;:%)]+$", "")
    local absolute = vim.fn.fnamemodify(cleaned, ":p")
    if absolute == "" then
        return nil
    end
    if vim.fn.filereadable(absolute) ~= 1 then
        return nil
    end
    return absolute
end

local function parse_text_references(text)
    local refs = {}
    if not text or text == "" then
        return refs
    end

    for _, raw_line in ipairs(vim.split(text, "\n", { plain = true })) do
        local message = vim.trim(raw_line)
        if message ~= "" then
            local offset = 1
            while offset <= #raw_line do
                local start_col, end_col, file_path, line_no = raw_line:find("([%w%._%-%/%\\]+):(%d+)", offset)
                if not start_col then break end
                local abs = normalize_path(file_path)
                local lnum = tonumber(line_no)
                if abs and lnum then
                    table.insert(refs, {
                        path = abs,
                        lnum = math.max(lnum - 1, 0),
                        message = message,
                        start_col = start_col - 1,
                        end_col = end_col,
                    })
                end
                offset = end_col + 1
            end
        end
    end

    return refs
end

function M.parse_file_line_references(text)
    return parse_text_references(text)
end

function M.reference_from_line(line, col)
    local refs = parse_text_references(line or "")
    if #refs == 0 then return nil end
    if col then
        for _, ref in ipairs(refs) do
            if col >= ref.start_col and col < ref.end_col then
                return ref
            end
        end
    end
    return refs[1]
end

function M.reference_under_cursor(bufnr)
    bufnr = bufnr or vim.api.nvim_get_current_buf()
    if not vim.api.nvim_buf_is_valid(bufnr) then return nil end
    local cursor = vim.api.nvim_win_get_cursor(0)
    local line = vim.api.nvim_buf_get_lines(bufnr, cursor[1] - 1, cursor[1], false)[1] or ""
    return M.reference_from_line(line, cursor[2])
end

function M.diagnostic_reference_under_cursor(bufnr)
    bufnr = bufnr or vim.api.nvim_get_current_buf()
    if not vim.api.nvim_buf_is_valid(bufnr) then return nil end
    local row = math.max(vim.api.nvim_win_get_cursor(0)[1] - 1, 0)
    local diags = vim.diagnostic.get(bufnr, { lnum = row, namespace = M.ns })
    if #diags == 0 then return nil end
    for _, diag in ipairs(diags) do
        local ref = M.reference_from_line(diag.message or "")
        if ref then return ref end
    end
    local name = vim.api.nvim_buf_get_name(bufnr)
    if name == "" then return nil end
    return {
        path = vim.fn.fnamemodify(name, ":p"),
        lnum = row,
        message = diags[1].message or "",
    }
end

function M.clear(opts)
    for _, bufnr in ipairs(vim.api.nvim_list_bufs()) do
        if vim.api.nvim_buf_is_valid(bufnr) then
            vim.diagnostic.reset(M.ns, bufnr)
        end
    end
    if not (opts and opts.silent) then
        emit_suggestions_changed()
    end
end

function M.apply_from_text(text)
    if not config.get("diagnostics_enabled") then
        return
    end

    M.clear({ silent = true })

    local refs = parse_text_references(text)
    if #refs == 0 then
        emit_suggestions_changed()
        return
    end

    local by_buf = {}
    for _, ref in ipairs(refs) do
        local bufnr = vim.fn.bufnr(ref.path, true)
        if bufnr ~= -1 then
            by_buf[bufnr] = by_buf[bufnr] or {}
            table.insert(by_buf[bufnr], {
                lnum = ref.lnum,
                col = 0,
                severity = vim.diagnostic.severity.HINT,
                message = ref.message,
                source = "poor-cli",
            })
        end
    end

    for bufnr, diagnostics in pairs(by_buf) do
        vim.diagnostic.set(M.ns, bufnr, diagnostics, {
            virtual_text = true,
            signs = false,
            underline = true,
            severity_sort = true,
        })
        local ok, dap = pcall(require, "poor-cli.integrations.dap")
        if ok and type(dap.attach) == "function" then
            dap.attach(bufnr)
        end
    end
    emit_suggestions_changed()
end

function M.toggle()
    local enabled = not config.get("diagnostics_enabled")
    config.config.diagnostics_enabled = enabled

    if not enabled then
        M.clear()
    end

    require("poor-cli.notify").notify(
        "[poor-cli] Diagnostics " .. (enabled and "enabled" or "disabled"),
        vim.log.levels.INFO
    )

    return enabled
end

--- Gather LSP diagnostics for the current buffer and format as context string.
--- Automatically injected when user asks about errors/warnings.
function M.get_buffer_diagnostics(bufnr)
    bufnr = bufnr or vim.api.nvim_get_current_buf()
    local diags = vim.diagnostic.get(bufnr)
    if #diags == 0 then
        return nil
    end
    local fname = vim.api.nvim_buf_get_name(bufnr)
    local lines = { "[LSP Diagnostics for " .. vim.fn.fnamemodify(fname, ":~:.") .. "]" }
    local severity_map = { "ERROR", "WARN", "INFO", "HINT" }
    for _, d in ipairs(diags) do
        local sev = severity_map[d.severity] or "UNKNOWN"
        local src = d.source and (" (" .. d.source .. ")") or ""
        table.insert(lines, string.format(
            "  L%d: [%s]%s %s",
            (d.lnum or 0) + 1, sev, src, d.message or ""
        ))
    end
    return table.concat(lines, "\n")
end

--- Build diagnostics context for all open buffers with errors/warnings.
function M.get_workspace_diagnostics_summary()
    local parts = {}
    for _, bufnr in ipairs(vim.api.nvim_list_bufs()) do
        if vim.api.nvim_buf_is_loaded(bufnr) then
            local ctx = M.get_buffer_diagnostics(bufnr)
            if ctx then
                table.insert(parts, ctx)
            end
        end
    end
    if #parts == 0 then
        return nil
    end
    return table.concat(parts, "\n\n")
end

return M
