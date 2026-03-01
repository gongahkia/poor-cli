-- poor-cli/inline.lua
-- Inline ghost text completion (like Windsurf/Copilot)

local config = require("poor-cli.config")
local rpc = require("poor-cli.rpc")

local M = {}

-- Namespace for extmarks
M.ns_id = vim.api.nvim_create_namespace("poor-cli-inline")

-- Current completion state
M.current_completion = nil  -- { bufnr, line, col, text }
M.inline_request_token = 0
M.pending_inline_request = nil  -- { token, request_id, bufnr, line, col, changedtick }
local cancel_pending_inline_request

local function create_inline_request_context(bufnr, line, col)
    cancel_pending_inline_request()

    M.inline_request_token = M.inline_request_token + 1
    local context = {
        token = M.inline_request_token,
        bufnr = bufnr,
        line = line,
        col = col,
        changedtick = vim.api.nvim_buf_get_changedtick(bufnr),
    }
    M.pending_inline_request = context
    return context
end

local function is_request_active(context)
    return M.pending_inline_request
        and M.pending_inline_request.token == context.token
end

local function clear_request_if_active(context)
    if is_request_active(context) then
        M.pending_inline_request = nil
    end
end

cancel_pending_inline_request = function()
    local context = M.pending_inline_request
    if not context then
        return
    end

    -- Remove callback dispatch for the stale in-flight request.
    if context.request_id and rpc.cancel_request then
        rpc.cancel_request(context.request_id)
    elseif context.request_id and rpc.pending then
        rpc.pending[context.request_id] = nil
    end

    M.pending_inline_request = nil
end

local function is_request_stale(context)
    if not vim.api.nvim_buf_is_valid(context.bufnr) then
        return true
    end

    if vim.api.nvim_get_current_buf() ~= context.bufnr then
        return true
    end

    local cursor = vim.api.nvim_win_get_cursor(0)
    if cursor[1] ~= context.line or cursor[2] ~= context.col then
        return true
    end

    local changedtick = vim.api.nvim_buf_get_changedtick(context.bufnr)
    return changedtick ~= context.changedtick
end

local function cancel_if_request_stale()
    local context = M.pending_inline_request
    if context and is_request_stale(context) then
        cancel_pending_inline_request()
    end
end

local function handle_inline_response(context, result, err)
    if not is_request_active(context) then
        return
    end

    if err then
        clear_request_if_active(context)
        vim.notify("[poor-cli] Completion error: " .. vim.inspect(err), vim.log.levels.ERROR)
        return
    end

    if not result or not result.completion then
        clear_request_if_active(context)
        return
    end

    vim.schedule(function()
        if not is_request_active(context) then
            return
        end

        if is_request_stale(context) then
            clear_request_if_active(context)
            return
        end

        clear_request_if_active(context)
        M.show_ghost_text(result.completion)
    end)
end

local request_cancel_group = vim.api.nvim_create_augroup("poor-cli-inline-request-cancel", { clear = true })

vim.api.nvim_create_autocmd({ "CursorMoved", "CursorMovedI", "TextChanged", "TextChangedI", "BufLeave" }, {
    group = request_cancel_group,
    callback = function()
        cancel_if_request_stale()
    end,
})

local function byte_len(text)
    return vim.fn.strlen(text or "")
end

local function split_line_at_byte_col(line_text, byte_col)
    local max_col = byte_len(line_text)
    local safe_col = math.max(0, math.min(byte_col, max_col))
    local before = line_text:sub(1, safe_col)
    local after = line_text:sub(safe_col + 1)
    return before, after, safe_col
end

-- Show ghost text at cursor position
function M.show_ghost_text(text)
    if not text or text == "" then
        return
    end
    
    local bufnr = vim.api.nvim_get_current_buf()
    local cursor = vim.api.nvim_win_get_cursor(0)
    local line = cursor[1] - 1  -- 0-indexed
    local col = cursor[2]
    
    -- Clear old ghost text
    M.clear_ghost_text()
    
    -- Split text into lines for multi-line ghost text
    local lines = vim.split(text, "\n", { plain = true })
    
    -- Store completion state
    M.current_completion = {
        bufnr = bufnr,
        line = line,
        col = col,
        text = text,
    }
    
    -- Create extmark with virtual text
    if #lines == 1 then
        -- Single line - inline virtual text
        vim.api.nvim_buf_set_extmark(bufnr, M.ns_id, line, col, {
            virt_text = {{ lines[1], config.get("ghost_text_hl") }},
            virt_text_pos = "inline",
        })
    else
        -- Multi-line - first line inline, rest as virtual lines
        vim.api.nvim_buf_set_extmark(bufnr, M.ns_id, line, col, {
            virt_text = {{ lines[1], config.get("ghost_text_hl") }},
            virt_text_pos = "inline",
            virt_lines = vim.tbl_map(function(l)
                return {{ l, config.get("ghost_text_hl") }}
            end, vim.list_slice(lines, 2)),
        })
    end
end

-- Clear all ghost text
function M.clear_ghost_text()
    local bufnr = vim.api.nvim_get_current_buf()
    vim.api.nvim_buf_clear_namespace(bufnr, M.ns_id, 0, -1)
    M.current_completion = nil
end

-- Accept the current completion
function M.accept()
    if not M.current_completion then
        return false
    end
    
    local comp = M.current_completion
    local bufnr = comp.bufnr
    local line = comp.line
    local col = comp.col
    local text = comp.text
    
    -- Clear ghost text first
    M.clear_ghost_text()
    
    -- Insert the text at cursor position
    local lines = vim.split(text, "\n", { plain = true })
    
    if #lines == 1 then
        -- Single line - insert inline
        local current_line = vim.api.nvim_buf_get_lines(bufnr, line, line + 1, false)[1] or ""
        local before, after, safe_col = split_line_at_byte_col(current_line, col)
        local new_line = before .. text .. after
        vim.api.nvim_buf_set_lines(bufnr, line, line + 1, false, { new_line })
        
        -- Move cursor to end of inserted text
        vim.api.nvim_win_set_cursor(0, { line + 1, safe_col + byte_len(text) })
    else
        -- Multi-line insert
        local current_line = vim.api.nvim_buf_get_lines(bufnr, line, line + 1, false)[1] or ""
        local before, after = split_line_at_byte_col(current_line, col)
        
        -- First line gets the prefix
        lines[1] = before .. lines[1]
        -- Last line gets the suffix
        lines[#lines] = lines[#lines] .. after
        
        vim.api.nvim_buf_set_lines(bufnr, line, line + 1, false, lines)
        
        -- Move cursor to end of inserted text
        local last_line = line + #lines
        local last_col = byte_len(lines[#lines]) - byte_len(after)
        vim.api.nvim_win_set_cursor(0, { last_line, last_col })
    end
    
    return true
end

-- Dismiss the current completion
function M.dismiss()
    M.clear_ghost_text()
end

-- Trigger inline completion
function M.trigger()
    if not rpc.is_running() then
        vim.notify("[poor-cli] Server not running", vim.log.levels.WARN)
        return
    end
    
    -- Clear any existing completion
    M.clear_ghost_text()
    
    -- Get buffer info
    local bufnr = vim.api.nvim_get_current_buf()
    local cursor = vim.api.nvim_win_get_cursor(0)
    local line = cursor[1]
    local col = cursor[2]
    
    -- Get buffer content
    local lines = vim.api.nvim_buf_get_lines(bufnr, 0, -1, false)
    local total_lines = #lines
    
    -- Split into before/after cursor
    local code_before = table.concat(vim.list_slice(lines, 1, line - 1), "\n")
    if line <= total_lines then
        local current_line = lines[line] or ""
        local current_prefix = current_line:sub(1, col)
        if code_before ~= "" then
            code_before = code_before .. "\n" .. current_prefix
        else
            code_before = current_prefix
        end
    end
    
    local code_after = ""
    if line <= total_lines then
        local current_line = lines[line] or ""
        code_after = current_line:sub(col + 1)
    end
    if line < total_lines then
        code_after = code_after .. "\n" .. table.concat(vim.list_slice(lines, line + 1), "\n")
    end
    
    -- Get file info
    local file_path = vim.fn.expand("%:p")
    local language = vim.bo[bufnr].filetype
    
    -- Request completion
    local request_context = create_inline_request_context(bufnr, line, col)

    local request_id = rpc.request("poor-cli/inlineComplete", {
        codeBefore = code_before,
        codeAfter = code_after,
        instruction = "",
        filePath = file_path,
        language = language,
    }, function(result, err)
        handle_inline_response(request_context, result, err)
    end)

    request_context.request_id = request_id
    if not request_id then
        clear_request_if_active(request_context)
    end
end

-- Trigger with custom instruction
function M.trigger_with_instruction(instruction)
    if not instruction then
        vim.ui.input({ prompt = "Instruction: " }, function(input)
            if input and input ~= "" then
                M.trigger_with_instruction(input)
            end
        end)
        return
    end
    
    if not rpc.is_running() then
        vim.notify("[poor-cli] Server not running", vim.log.levels.WARN)
        return
    end
    
    M.clear_ghost_text()
    
    local bufnr = vim.api.nvim_get_current_buf()
    local cursor = vim.api.nvim_win_get_cursor(0)
    local line = cursor[1]
    local col = cursor[2]
    local lines = vim.api.nvim_buf_get_lines(bufnr, 0, -1, false)
    
    local code_before = table.concat(vim.list_slice(lines, 1, line - 1), "\n")
    if line <= #lines then
        local current_prefix = (lines[line] or ""):sub(1, col)
        if code_before ~= "" then
            code_before = code_before .. "\n" .. current_prefix
        else
            code_before = current_prefix
        end
    end
    
    local code_after = ""
    if line <= #lines then
        code_after = (lines[line] or ""):sub(col + 1)
    end
    if line < #lines then
        code_after = code_after .. "\n" .. table.concat(vim.list_slice(lines, line + 1), "\n")
    end
    
    local file_path = vim.fn.expand("%:p")
    local language = vim.bo[bufnr].filetype
    
    local request_context = create_inline_request_context(bufnr, line, col)

    local request_id = rpc.request("poor-cli/inlineComplete", {
        codeBefore = code_before,
        codeAfter = code_after,
        instruction = instruction,
        filePath = file_path,
        language = language,
    }, function(result, err)
        handle_inline_response(request_context, result, err)
    end)

    request_context.request_id = request_id
    if not request_id then
        clear_request_if_active(request_context)
    end
end

-- Complete visual selection with instruction
function M.complete_selection()
    local mode = vim.fn.mode()
    if mode ~= "v" and mode ~= "V" then
        vim.notify("[poor-cli] Select text first", vim.log.levels.WARN)
        return
    end
    
    -- Get selection
    local start_pos = vim.fn.getpos("'<")
    local end_pos = vim.fn.getpos("'>")
    local lines = vim.fn.getline(start_pos[2], end_pos[2])
    
    if type(lines) == "string" then
        lines = { lines }
    end
    
    local selected_text = table.concat(lines, "\n")
    
    vim.ui.input({ prompt = "Instruction: " }, function(instruction)
        if not instruction or instruction == "" then
            return
        end
        
        -- Request completion to replace selection
        rpc.request("poor-cli/chat", {
            message = "Refactor/modify this code according to the instruction. " ..
                      "Return ONLY the modified code, no explanations.\n\n" ..
                      "Instruction: " .. instruction .. "\n\n" ..
                      "Code:\n" .. selected_text,
        }, function(result, err)
            if err then
                vim.notify("[poor-cli] Error: " .. vim.inspect(err), vim.log.levels.ERROR)
                return
            end
            
            if result and result.content then
                vim.schedule(function()
                    -- Replace selection with result
                    local new_lines = vim.split(result.content, "\n", { plain = true })
                    vim.api.nvim_buf_set_lines(0, start_pos[2] - 1, end_pos[2], false, new_lines)
                end)
            end
        end)
    end)
end

-- Check if ghost text is visible
function M.has_completion()
    return M.current_completion ~= nil
end

return M
