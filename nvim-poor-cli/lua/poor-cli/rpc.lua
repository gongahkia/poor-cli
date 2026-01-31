-- poor-cli/rpc.lua
-- JSON-RPC client for communicating with poor-cli-server

local config = require("poor-cli.config")

local M = {}

-- State
M.job_id = nil
M.request_id = 0
M.pending = {}  -- Maps request_id to callback
M.buffer = ""   -- Accumulates partial messages

-- Start the server
function M.start()
    if M.job_id then
        vim.notify("[poor-cli] Server already running", vim.log.levels.WARN)
        return M.job_id
    end
    
    local cmd = config.get("server_cmd")
    if config.is_debug() then
        vim.notify("[poor-cli] Starting server: " .. cmd, vim.log.levels.DEBUG)
    end
    
    M.job_id = vim.fn.jobstart(cmd, {
        on_stdout = function(_, data, _)
            M.handle_stdout(data)
        end,
        on_stderr = function(_, data, _)
            M.handle_stderr(data)
        end,
        on_exit = function(_, code, _)
            M.handle_exit(code)
        end,
        stdin = "pipe",
        stdout_buffered = false,
        stderr_buffered = false,
    })
    
    if M.job_id <= 0 then
        vim.notify("[poor-cli] Failed to start server", vim.log.levels.ERROR)
        M.job_id = nil
        return nil
    end
    
    vim.notify("[poor-cli] Server started", vim.log.levels.INFO)
    return M.job_id
end

-- Stop the server
function M.stop()
    if M.job_id then
        vim.fn.jobstop(M.job_id)
        M.job_id = nil
        M.pending = {}
        M.buffer = ""
        vim.notify("[poor-cli] Server stopped", vim.log.levels.INFO)
    end
end

-- Check if server is running
function M.is_running()
    return M.job_id ~= nil
end

-- Send a request and wait for response
function M.request(method, params, callback)
    if not M.job_id then
        if callback then
            callback(nil, { message = "Server not running" })
        end
        return nil
    end
    
    M.request_id = M.request_id + 1
    local id = M.request_id
    
    local message = {
        jsonrpc = "2.0",
        id = id,
        method = method,
        params = params or {},
    }
    
    -- Store callback
    M.pending[id] = callback
    
    -- Send message
    M.send_message(message)
    
    if config.is_debug() then
        vim.notify("[poor-cli] Request " .. id .. ": " .. method, vim.log.levels.DEBUG)
    end
    
    return id
end

-- Send a notification (no response expected)
function M.notify(method, params)
    if not M.job_id then
        return
    end
    
    local message = {
        jsonrpc = "2.0",
        method = method,
        params = params or {},
    }
    
    M.send_message(message)
end

-- Send a JSON-RPC message
function M.send_message(message)
    local json = vim.fn.json_encode(message)
    local content = "Content-Length: " .. #json .. "\r\n\r\n" .. json
    
    vim.fn.chansend(M.job_id, content)
end

-- Handle stdout data
function M.handle_stdout(data)
    -- Accumulate data
    for _, chunk in ipairs(data) do
        M.buffer = M.buffer .. chunk
    end
    
    -- Try to parse complete messages
    while true do
        local message = M.parse_message()
        if not message then
            break
        end
        M.handle_response(message)
    end
end

-- Parse a complete message from buffer
function M.parse_message()
    -- Look for Content-Length header
    local header_end = M.buffer:find("\r\n\r\n")
    if not header_end then
        return nil
    end
    
    local header = M.buffer:sub(1, header_end - 1)
    local content_length = tonumber(header:match("Content%-Length:%s*(%d+)"))
    
    if not content_length then
        return nil
    end
    
    local body_start = header_end + 4
    local body_end = body_start + content_length - 1
    
    if #M.buffer < body_end then
        return nil  -- Not enough data yet
    end
    
    local body = M.buffer:sub(body_start, body_end)
    M.buffer = M.buffer:sub(body_end + 1)
    
    local ok, message = pcall(vim.fn.json_decode, body)
    if not ok then
        vim.notify("[poor-cli] Failed to parse JSON: " .. body, vim.log.levels.ERROR)
        return nil
    end
    
    return message
end

-- Handle a parsed response
function M.handle_response(message)
    if config.is_debug() then
        vim.notify("[poor-cli] Response: " .. vim.inspect(message), vim.log.levels.DEBUG)
    end
    
    -- Handle notifications (no id)
    if not message.id then
        M.handle_notification(message)
        return
    end
    
    -- Find and call callback
    local callback = M.pending[message.id]
    if callback then
        M.pending[message.id] = nil
        
        if message.error then
            callback(nil, message.error)
        else
            callback(message.result, nil)
        end
    end
end

-- Handle notifications from server
function M.handle_notification(message)
    if message.method == "poor-cli/streamChunk" then
        -- Handle streaming chunk
        local params = message.params or {}
        local request_id = params.requestId
        local chunk = params.chunk
        local done = params.done
        
        -- Emit event for streaming handlers
        vim.api.nvim_exec_autocmds("User", {
            pattern = "PoorCliStreamChunk",
            data = { request_id = request_id, chunk = chunk, done = done },
        })
    end
end

-- Handle stderr
function M.handle_stderr(data)
    for _, line in ipairs(data) do
        if line ~= "" then
            if config.is_debug() then
                vim.notify("[poor-cli server] " .. line, vim.log.levels.DEBUG)
            end
        end
    end
end

-- Handle server exit
function M.handle_exit(code)
    M.job_id = nil
    M.pending = {}
    M.buffer = ""
    
    if code ~= 0 then
        vim.notify("[poor-cli] Server exited with code " .. code, vim.log.levels.WARN)
    else
        if config.is_debug() then
            vim.notify("[poor-cli] Server exited normally", vim.log.levels.DEBUG)
        end
    end
end

return M
