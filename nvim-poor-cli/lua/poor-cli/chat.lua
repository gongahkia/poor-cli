-- poor-cli/chat.lua
-- Chat panel for AI conversations

local config = require("poor-cli.config")
local rpc = require("poor-cli.rpc")

local M = {}

-- State
M.buf = nil
M.win = nil
M.history = {}
M.input_buf = nil
M.input_win = nil
M.loading_ns = vim.api.nvim_create_namespace("poor-cli-chat-loading")
M.loading_marker = nil
M.streaming_buf_line = nil -- line where current streaming response starts
M.streaming_request_id = nil

-- Open chat panel
function M.open()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_set_current_win(M.win)
        return
    end
    
    -- Create buffer if needed
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        M.buf = vim.api.nvim_create_buf(false, true)
        vim.bo[M.buf].buftype = "nofile"
        vim.bo[M.buf].bufhidden = "hide"
        vim.bo[M.buf].swapfile = false
        vim.bo[M.buf].filetype = "markdown"
        vim.api.nvim_buf_set_name(M.buf, "[poor-cli chat]")
        
        -- Add welcome message
        local welcome = {
            "# poor-cli Chat",
            "",
            "Use `:PoorCliSend` or press `<CR>` at the bottom to send a message.",
            "",
            "---",
            "",
        }
        vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, welcome)
    end
    
    -- Open window
    local width = config.get("chat_width")
    local position = config.get("chat_position")
    
    if position == "right" then
        vim.cmd("botright " .. width .. "vsplit")
    else
        vim.cmd("topleft " .. width .. "vsplit")
    end
    
    M.win = vim.api.nvim_get_current_win()
    vim.api.nvim_win_set_buf(M.win, M.buf)
    
    -- Window options
    vim.wo[M.win].wrap = true
    vim.wo[M.win].linebreak = true
    vim.wo[M.win].number = false
    vim.wo[M.win].relativenumber = false
    vim.wo[M.win].signcolumn = "no"
    
    -- Move to end of buffer
    vim.cmd("normal! G")
    
    -- Setup keymaps for chat buffer
    M.setup_buffer_keymaps()
end

-- Close chat panel
function M.close()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_win_close(M.win, true)
        M.win = nil
    end
end

-- Toggle chat panel
function M.toggle()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        M.close()
    else
        M.open()
    end
end

-- Append a message to the chat buffer
function M.append_message(role, content)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    
    local lines = {}
    
    if role == "user" then
        table.insert(lines, "## 👤 You")
    else
        table.insert(lines, "## 🤖 Assistant")
    end
    
    table.insert(lines, "")
    
    -- Add content lines
    for _, line in ipairs(vim.split(content, "\n", { plain = true })) do
        table.insert(lines, line)
    end
    
    table.insert(lines, "")
    table.insert(lines, "---")
    table.insert(lines, "")
    
    -- Append to buffer
    local line_count = vim.api.nvim_buf_line_count(M.buf)
    vim.api.nvim_buf_set_lines(M.buf, line_count, line_count, false, lines)
    
    -- Scroll to bottom if window is open
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        local new_count = vim.api.nvim_buf_line_count(M.buf)
        vim.api.nvim_win_set_cursor(M.win, { new_count, 0 })
    end
    
    -- Store in history
    table.insert(M.history, { role = role, content = content })
end

-- Send a message (uses streaming endpoint when available)
function M.send(message)
    if not message or message == "" then
        return
    end

    if not rpc.is_running() then
        vim.notify("[poor-cli] Server not running", vim.log.levels.WARN)
        return
    end

    M.append_message("user", message)
    local context_files = M.get_context_files()

    -- Use streaming endpoint
    M.streaming_request_id = tostring(os.time()) .. "-" .. tostring(math.random(1000, 9999))
    M._start_streaming_block()

    rpc.request("poor-cli/chatStreaming", {
        message = message,
        contextFiles = context_files,
        requestId = M.streaming_request_id,
    }, function(result, err)
        vim.schedule(function()
            M._finalize_streaming_block()
            if err then
                M.append_message("assistant", "Error: " .. vim.inspect(err))
            end
        end)
    end)
end

-- Start a streaming assistant message block
function M._start_streaming_block()
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    local line_count = vim.api.nvim_buf_line_count(M.buf)
    local header = { "## 🤖 Assistant", "" }
    vim.api.nvim_buf_set_lines(M.buf, line_count, line_count, false, header)
    M.streaming_buf_line = line_count + #header -- 0-indexed line where text goes
end

-- Append a streaming chunk to the current block
function M._append_streaming_chunk(chunk)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    if not M.streaming_buf_line then
        return
    end
    if not chunk or chunk == "" then
        return
    end

    -- Get current last line of the streaming block
    local line_count = vim.api.nvim_buf_line_count(M.buf)
    local last_line_idx = line_count - 1
    local last_line = vim.api.nvim_buf_get_lines(M.buf, last_line_idx, line_count, false)[1] or ""

    -- Split chunk by newlines and append
    local parts = vim.split(chunk, "\n", { plain = true })
    if #parts == 1 then
        vim.api.nvim_buf_set_lines(M.buf, last_line_idx, line_count, false, { last_line .. parts[1] })
    else
        local lines = { last_line .. parts[1] }
        for i = 2, #parts do
            table.insert(lines, parts[i])
        end
        vim.api.nvim_buf_set_lines(M.buf, last_line_idx, line_count, false, lines)
    end

    -- Scroll to bottom
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        local new_count = vim.api.nvim_buf_line_count(M.buf)
        pcall(vim.api.nvim_win_set_cursor, M.win, { new_count, 0 })
    end
end

-- Finalize streaming block
function M._finalize_streaming_block()
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    if M.streaming_buf_line then
        local line_count = vim.api.nvim_buf_line_count(M.buf)
        vim.api.nvim_buf_set_lines(M.buf, line_count, line_count, false, { "", "---", "" })
    end
    M.streaming_buf_line = nil
    M.streaming_request_id = nil
end

-- Setup streaming autocmds
function M.setup_streaming_autocmds()
    local group = vim.api.nvim_create_augroup("PoorCliChatStreaming", { clear = true })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCliStreamChunk",
        callback = function(ev)
            local data = ev.data or {}
            if data.done then
                vim.schedule(function()
                    M._finalize_streaming_block()
                end)
            elseif data.chunk and data.chunk ~= "" then
                vim.schedule(function()
                    M._append_streaming_chunk(data.chunk)
                end)
            end
        end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCliToolEvent",
        callback = function(ev)
            local data = ev.data or {}
            vim.schedule(function()
                if data.event_type == "tool_call_start" then
                    M._append_tool_call(data.tool_name, data.tool_args)
                elseif data.event_type == "tool_result" then
                    local diff = data.diff or ""
                    if diff ~= "" then
                        M._append_diff_view(data.tool_name, diff)
                    else
                        M._append_tool_result(data.tool_name, data.tool_result)
                    end
                end
            end)
        end,
    })
end

-- Append a tool call block to the chat buffer
function M._append_tool_call(name, args)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    local line_count = vim.api.nvim_buf_line_count(M.buf)
    local args_str = type(args) == "table" and vim.inspect(args) or tostring(args or "")
    local lines = { "**🔧 " .. (name or "tool") .. "**", "```", args_str, "```", "" }
    vim.api.nvim_buf_set_lines(M.buf, line_count, line_count, false, lines)
end

-- Append a tool result block
function M._append_tool_result(name, result)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    local line_count = vim.api.nvim_buf_line_count(M.buf)
    local result_str = tostring(result or "")
    if #result_str > 500 then
        result_str = result_str:sub(1, 500) .. "…"
    end
    local lines = { "**✓ " .. (name or "tool") .. " result**", "```", result_str, "```", "" }
    vim.api.nvim_buf_set_lines(M.buf, line_count, line_count, false, lines)
end

-- Append a diff view block
function M._append_diff_view(name, diff_text)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    local line_count = vim.api.nvim_buf_line_count(M.buf)
    local lines = { "**📝 " .. (name or "edit") .. " diff**", "```diff" }
    for _, line in ipairs(vim.split(diff_text, "\n", { plain = true })) do
        table.insert(lines, line)
    end
    table.insert(lines, "```")
    table.insert(lines, "")
    vim.api.nvim_buf_set_lines(M.buf, line_count, line_count, false, lines)
end

-- Get list of open buffer file paths for context
function M.get_context_files()
    local files = {}
    local seen = {}
    local max_context_files = tonumber(config.get("max_context_files")) or 20
    local should_cap = max_context_files > 0
    
    for _, bufnr in ipairs(vim.api.nvim_list_bufs()) do
        if vim.api.nvim_buf_is_loaded(bufnr) then
            local name = vim.api.nvim_buf_get_name(bufnr)
            if name ~= "" and vim.fn.filereadable(name) == 1 then
                -- Only include code files
                local ft = vim.bo[bufnr].filetype
                if ft ~= "" and ft ~= "help" and ft ~= "markdown" then
                    local absolute = vim.fn.fnamemodify(name, ":p")
                    local canonical = vim.loop.fs_realpath(absolute) or absolute

                    if canonical ~= "" and not seen[canonical] then
                        seen[canonical] = true
                        table.insert(files, canonical)
                        if should_cap and #files >= max_context_files then
                            break
                        end
                    end
                end
            end
        end
    end
    
    return files
end

-- Setup keymaps for chat buffer
function M.setup_buffer_keymaps()
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    
    -- q to close
    vim.keymap.set("n", "q", function()
        M.close()
    end, { buffer = M.buf, desc = "Close chat" })
    
    -- <CR> to prompt for message
    vim.keymap.set("n", "<CR>", function()
        M.prompt_and_send()
    end, { buffer = M.buf, desc = "Send message" })
end

-- Prompt for message and send
function M.prompt_and_send()
    vim.ui.input({ prompt = "Message: " }, function(input)
        if input and input ~= "" then
            M.send(input)
        end
    end)
end

-- Append loading indicator
function M.append_loading()
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end

    -- Keep only one loading block at a time.
    M.remove_loading()

    local line_count = vim.api.nvim_buf_line_count(M.buf)
    local loading_lines = {
        "## 🤖 Assistant",
        "",
        "_Thinking..._",
        "",
    }

    vim.api.nvim_buf_set_lines(M.buf, line_count, line_count, false, loading_lines)
    M.loading_marker = vim.api.nvim_buf_set_extmark(M.buf, M.loading_ns, line_count, 0, {
        end_row = line_count + #loading_lines,
        end_col = 0,
        right_gravity = false,
    })
end

-- Remove loading indicator
function M.remove_loading()
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end

    if not M.loading_marker then
        return
    end

    local marker = vim.api.nvim_buf_get_extmark_by_id(
        M.buf,
        M.loading_ns,
        M.loading_marker,
        { details = true }
    )

    if marker and #marker >= 3 then
        local start_row = marker[1]
        local details = marker[3] or {}
        local end_row = details.end_row
        if end_row and end_row >= start_row then
            vim.api.nvim_buf_set_lines(M.buf, start_row, end_row, false, {})
        end
    end

    pcall(vim.api.nvim_buf_del_extmark, M.buf, M.loading_ns, M.loading_marker)
    M.loading_marker = nil
end

-- Send with current visual selection
function M.send_with_selection()
    local mode = vim.fn.mode()
    if mode ~= "v" and mode ~= "V" then
        vim.notify("[poor-cli] Select text first", vim.log.levels.WARN)
        return
    end
    
    -- Get selection
    vim.cmd('normal! "xy')
    local selected_text = vim.fn.getreg("x")
    
    if not selected_text or selected_text == "" then
        return
    end
    
    -- Open chat if not open
    M.open()
    
    -- Prompt for question about the selection
    vim.ui.input({ prompt = "Ask about selection: " }, function(question)
        if not question or question == "" then
            question = "Please explain this code."
        end
        
        local message = question .. "\n\n```\n" .. selected_text .. "\n```"
        M.send(message)
    end)
end

-- Clear chat history
function M.clear()
    if M.buf and vim.api.nvim_buf_is_valid(M.buf) then
        local welcome = {
            "# poor-cli Chat",
            "",
            "Use `:PoorCliSend` or press `<CR>` at the bottom to send a message.",
            "",
            "---",
            "",
        }
        vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, welcome)
    end
    M.history = {}
    
    -- Also clear server history
    if rpc.is_running() then
        rpc.request("poor-cli/clearHistory", {}, function() end)
    end
end

return M
