-- poor-cli/inline.lua
-- Inline ghost text completion (like Windsurf/Copilot)

local config = require("poor-cli.config")
local rpc = require("poor-cli.rpc")

local M = {}

-- Namespace for extmarks
M.ns_id = vim.api.nvim_create_namespace("poor-cli-inline")

-- Current completion state
M.current_completion = nil  -- { bufnr, line, col, text }

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
        local new_line = current_line:sub(1, col) .. text .. current_line:sub(col + 1)
        vim.api.nvim_buf_set_lines(bufnr, line, line + 1, false, { new_line })
        
        -- Move cursor to end of inserted text
        vim.api.nvim_win_set_cursor(0, { line + 1, col + #text })
    else
        -- Multi-line insert
        local current_line = vim.api.nvim_buf_get_lines(bufnr, line, line + 1, false)[1] or ""
        local before = current_line:sub(1, col)
        local after = current_line:sub(col + 1)
        
        -- First line gets the prefix
        lines[1] = before .. lines[1]
        -- Last line gets the suffix
        lines[#lines] = lines[#lines] .. after
        
        vim.api.nvim_buf_set_lines(bufnr, line, line + 1, false, lines)
        
        -- Move cursor to end of inserted text
        local last_line = line + #lines
        local last_col = #lines[#lines] - #after
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
        code_before = code_before .. "\n" .. current_line:sub(1, col)
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
    rpc.request("poor-cli/inlineComplete", {
        codeBefore = code_before,
        codeAfter = code_after,
        instruction = "",
        filePath = file_path,
        language = language,
    }, function(result, err)
        if err then
            vim.notify("[poor-cli] Completion error: " .. vim.inspect(err), vim.log.levels.ERROR)
            return
        end
        
        if result and result.completion then
            vim.schedule(function()
                M.show_ghost_text(result.completion)
            end)
        end
    end)
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
        code_before = code_before .. "\n" .. (lines[line] or ""):sub(1, col)
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
    
    rpc.request("poor-cli/inlineComplete", {
        codeBefore = code_before,
        codeAfter = code_after,
        instruction = instruction,
        filePath = file_path,
        language = language,
    }, function(result, err)
        if err then
            vim.notify("[poor-cli] Completion error: " .. vim.inspect(err), vim.log.levels.ERROR)
            return
        end
        
        if result and result.completion then
            vim.schedule(function()
                M.show_ghost_text(result.completion)
            end)
        end
    end)
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
