-- poor-cli/lsp.lua
-- LSP integration for using diagnostics as AI context

local M = {}

-- Get diagnostics for the current buffer
function M.get_buffer_diagnostics(bufnr)
    bufnr = bufnr or vim.api.nvim_get_current_buf()
    
    local diagnostics = vim.diagnostic.get(bufnr)
    if #diagnostics == 0 then
        return nil
    end
    
    local result = {}
    for _, d in ipairs(diagnostics) do
        table.insert(result, {
            line = d.lnum + 1,  -- Convert to 1-indexed
            col = d.col + 1,
            severity = vim.diagnostic.severity[d.severity] or "Unknown",
            message = d.message,
            source = d.source or "unknown",
            code = d.code,
        })
    end
    
    return result
end

-- Format diagnostics for AI prompt
function M.format_diagnostics_for_prompt(diagnostics)
    if not diagnostics or #diagnostics == 0 then
        return ""
    end
    
    local lines = { "## Current Diagnostics/Errors\n" }
    
    for _, d in ipairs(diagnostics) do
        local severity_icon = ({
            Error = "❌",
            Warn = "⚠️",
            Info = "ℹ️",
            Hint = "💡",
        })[d.severity] or "•"
        
        table.insert(lines, string.format(
            "%s Line %d: [%s] %s",
            severity_icon,
            d.line,
            d.source,
            d.message
        ))
    end
    
    table.insert(lines, "")
    return table.concat(lines, "\n")
end

-- Get diagnostics context for current cursor position
function M.get_cursor_diagnostics()
    local cursor = vim.api.nvim_win_get_cursor(0)
    local line = cursor[1] - 1  -- 0-indexed for vim.diagnostic
    
    local diagnostics = vim.diagnostic.get(0, { lnum = line })
    return M.format_diagnostics_for_prompt(
        vim.tbl_map(function(d)
            return {
                line = d.lnum + 1,
                col = d.col + 1,
                severity = vim.diagnostic.severity[d.severity],
                message = d.message,
                source = d.source,
            }
        end, diagnostics)
    )
end

-- Get all errors (severity = Error) in buffer
function M.get_errors()
    local diagnostics = vim.diagnostic.get(0, { severity = vim.diagnostic.severity.ERROR })
    return M.format_diagnostics_for_prompt(
        vim.tbl_map(function(d)
            return {
                line = d.lnum + 1,
                col = d.col + 1,
                severity = "Error",
                message = d.message,
                source = d.source,
            }
        end, diagnostics)
    )
end

-- Get code actions available at cursor (if LSP supports it)
function M.get_code_actions_sync(timeout_ms)
    timeout_ms = timeout_ms or 1000
    
    local params = vim.lsp.util.make_range_params()
    params.context = { diagnostics = vim.diagnostic.get(0) }
    
    local results = vim.lsp.buf_request_sync(0, "textDocument/codeAction", params, timeout_ms)
    if not results then
        return nil
    end
    
    local actions = {}
    for _, res in pairs(results) do
        if res.result then
            for _, action in ipairs(res.result) do
                table.insert(actions, {
                    title = action.title,
                    kind = action.kind,
                })
            end
        end
    end
    
    return actions
end

-- Format code actions for prompt
function M.format_code_actions_for_prompt(actions)
    if not actions or #actions == 0 then
        return ""
    end
    
    local lines = { "## Available Code Actions\n" }
    for _, action in ipairs(actions) do
        table.insert(lines, string.format("- %s", action.title))
    end
    table.insert(lines, "")
    
    return table.concat(lines, "\n")
end

-- Get hover information at cursor
function M.get_hover_info_sync(timeout_ms)
    timeout_ms = timeout_ms or 1000
    
    local params = vim.lsp.util.make_position_params()
    local results = vim.lsp.buf_request_sync(0, "textDocument/hover", params, timeout_ms)
    
    if not results then
        return nil
    end
    
    for _, res in pairs(results) do
        if res.result and res.result.contents then
            local contents = res.result.contents
            if type(contents) == "string" then
                return contents
            elseif type(contents) == "table" then
                if contents.value then
                    return contents.value
                elseif contents[1] then
                    return type(contents[1]) == "string" and contents[1] or contents[1].value
                end
            end
        end
    end
    
    return nil
end

-- Get full LSP context for AI (diagnostics + hover + actions)
function M.get_full_lsp_context()
    local parts = {}
    
    -- Diagnostics
    local diagnostics = M.get_buffer_diagnostics()
    if diagnostics and #diagnostics > 0 then
        table.insert(parts, M.format_diagnostics_for_prompt(diagnostics))
    end
    
    -- Hover info at cursor
    local hover = M.get_hover_info_sync(500)
    if hover then
        table.insert(parts, "## Symbol Info at Cursor\n```\n" .. hover .. "\n```\n")
    end
    
    return table.concat(parts, "\n")
end

-- Command: Fix diagnostics with AI
function M.fix_diagnostics()
    local rpc = require("poor-cli.rpc")
    local chat = require("poor-cli.chat")
    
    if not rpc.is_running() then
        vim.notify("[poor-cli] Server not running", vim.log.levels.WARN)
        return
    end
    
    local diagnostics = M.get_buffer_diagnostics()
    if not diagnostics or #diagnostics == 0 then
        vim.notify("[poor-cli] No diagnostics in current buffer", vim.log.levels.INFO)
        return
    end
    
    -- Get current buffer content
    local lines = vim.api.nvim_buf_get_lines(0, 0, -1, false)
    local content = table.concat(lines, "\n")
    local language = vim.bo.filetype
    
    local diagnostics_text = M.format_diagnostics_for_prompt(diagnostics)
    
    chat.open()
    
    vim.notify("[poor-cli] Analyzing diagnostics...", vim.log.levels.INFO)
    
    rpc.request("poor-cli/chat", {
        message = "Fix the following issues in this " .. language .. " code:\n\n" ..
                  diagnostics_text .. "\n\n```" .. language .. "\n" .. content .. "\n```\n\n" ..
                  "Provide the corrected code and explain each fix.",
    }, function(result, err)
        vim.schedule(function()
            if err then
                chat.append_message("assistant", "Error: " .. vim.inspect(err))
            elseif result and result.content then
                chat.append_message("user", "Fix diagnostics:\n" .. diagnostics_text)
                chat.append_message("assistant", result.content)
            end
        end)
    end)
end

return M
