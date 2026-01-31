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

-- Send a message
function M.send(message)
    if not message or message == "" then
        return
    end
    
    if not rpc.is_running() then
        vim.notify("[poor-cli] Server not running", vim.log.levels.WARN)
        return
    end
    
    -- Append user message
    M.append_message("user", message)
    
    -- Show loading indicator
    M.append_loading()
    
    -- Get context files (open buffers)
    local context_files = M.get_context_files()
    
    -- Send request
    rpc.request("poor-cli/chat", {
        message = message,
        contextFiles = context_files,
    }, function(result, err)
        vim.schedule(function()
            -- Remove loading indicator
            M.remove_loading()
            
            if err then
                M.append_message("assistant", "Error: " .. vim.inspect(err))
                return
            end
            
            if result and result.content then
                M.append_message("assistant", result.content)
            end
        end)
    end)
end

-- Get list of open buffer file paths for context
function M.get_context_files()
    local files = {}
    
    for _, bufnr in ipairs(vim.api.nvim_list_bufs()) do
        if vim.api.nvim_buf_is_loaded(bufnr) then
            local name = vim.api.nvim_buf_get_name(bufnr)
            if name ~= "" and vim.fn.filereadable(name) == 1 then
                -- Only include code files
                local ft = vim.bo[bufnr].filetype
                if ft ~= "" and ft ~= "help" and ft ~= "markdown" then
                    table.insert(files, name)
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
    
    local line_count = vim.api.nvim_buf_line_count(M.buf)
    vim.api.nvim_buf_set_lines(M.buf, line_count, line_count, false, {
        "## 🤖 Assistant",
        "",
        "_Thinking..._",
        "",
    })
end

-- Remove loading indicator
function M.remove_loading()
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    
    local line_count = vim.api.nvim_buf_line_count(M.buf)
    
    -- Find and remove the loading indicator
    local lines = vim.api.nvim_buf_get_lines(M.buf, math.max(0, line_count - 10), line_count, false)
    
    for i = #lines, 1, -1 do
        if lines[i] == "_Thinking..._" then
            -- Remove the loading block (header, empty, thinking, empty)
            local start_line = line_count - (#lines - i) - 2
            vim.api.nvim_buf_set_lines(M.buf, start_line, line_count, false, {})
            break
        end
    end
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
