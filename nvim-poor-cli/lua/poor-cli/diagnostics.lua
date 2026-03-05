-- poor-cli/diagnostics.lua
-- Inline diagnostics extracted from assistant file:line suggestions.

local config = require("poor-cli.config")

local M = {}

M.ns = vim.api.nvim_create_namespace("poor-cli-diagnostics")

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
        local line = vim.trim(raw_line)
        if line ~= "" then
            for file_path, line_no in line:gmatch("([%w%._%-%/%\\]+):(%d+)") do
                local abs = normalize_path(file_path)
                local lnum = tonumber(line_no)
                if abs and lnum then
                    table.insert(refs, {
                        path = abs,
                        lnum = math.max(lnum - 1, 0),
                        message = line,
                    })
                end
            end
        end
    end

    return refs
end

function M.clear()
    for _, bufnr in ipairs(vim.api.nvim_list_bufs()) do
        if vim.api.nvim_buf_is_valid(bufnr) then
            vim.diagnostic.reset(M.ns, bufnr)
        end
    end
end

function M.apply_from_text(text)
    if not config.get("diagnostics_enabled") then
        return
    end

    M.clear()

    local refs = parse_text_references(text)
    if #refs == 0 then
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
    end
end

function M.toggle()
    local enabled = not config.get("diagnostics_enabled")
    config.config.diagnostics_enabled = enabled

    if not enabled then
        M.clear()
    end

    vim.notify(
        "[poor-cli] Diagnostics " .. (enabled and "enabled" or "disabled"),
        vim.log.levels.INFO
    )

    return enabled
end

return M
