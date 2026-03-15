-- poor-cli/rpc.lua
-- JSON-RPC client for communicating with poor-cli-server

local config = require("poor-cli.config")

local M = {}

-- State
M.job_id = nil
M.request_id = 0
M.pending = {}  -- Maps request_id to callback
M.pending_timers = {} -- Maps request_id to timeout timer
M.buffer = ""   -- Accumulates partial messages
M.manual_stop = false
M.restart_attempt = 0
M.restart_timer = nil
M.capabilities = nil
M.multiplayer_state = {
    enabled = false,
    room = "",
    role = "",
    local_connection_id = "",
    member_count = 0,
    queue_depth = 0,
    active_connection_id = "",
    lobby_enabled = false,
    preset = "",
    last_event_type = "",
    members = {},
    last_suggestion = nil,
}

local function clear_request_timer(id)
    local timer = M.pending_timers[id]
    if not timer then
        return
    end

    M.pending_timers[id] = nil
    pcall(function()
        timer:stop()
        timer:close()
    end)
end

local function clear_all_request_timers()
    for id, _ in pairs(M.pending_timers) do
        clear_request_timer(id)
    end
end

local function clear_restart_timer()
    if not M.restart_timer then
        return
    end

    local timer = M.restart_timer
    M.restart_timer = nil
    pcall(function()
        timer:stop()
        timer:close()
    end)
end

local function fresh_multiplayer_state()
    return {
        enabled = false,
        room = "",
        role = "",
        local_connection_id = "",
        member_count = 0,
        queue_depth = 0,
        active_connection_id = "",
        lobby_enabled = false,
        preset = "",
        last_event_type = "",
        members = {},
        last_suggestion = nil,
    }
end

function M.reset_session_state()
    M.capabilities = nil
    M.multiplayer_state = fresh_multiplayer_state()
end

function M.client_capabilities()
    return {
        uiSurface = "neovim",
        streaming = true,
        reviewFlows = {
            permissionRequests = true,
            planReview = true,
        },
        multiplayer = {
            events = true,
            roleUpdates = true,
            suggestions = true,
            roomPresence = true,
            roomActions = {
                suggestText = true,
                passDriver = true,
                listRoomMembers = true,
            },
        },
    }
end

function M.capture_initialize_result(result)
    local caps = result and result.capabilities or nil
    if type(caps) ~= "table" then
        M.capabilities = nil
        return
    end

    M.capabilities = caps
    local multiplayer = caps.multiplayer
    if type(multiplayer) ~= "table" then
        return
    end

    M.multiplayer_state.enabled = multiplayer.enabled == true
    M.multiplayer_state.room = multiplayer.room or ""
    M.multiplayer_state.role = multiplayer.role or ""
    M.multiplayer_state.local_connection_id = multiplayer.connectionId or ""
    M.multiplayer_state.lobby_enabled = multiplayer.lobbyEnabled == true
    M.multiplayer_state.preset = multiplayer.preset or ""
end

function M.get_capabilities()
    return M.capabilities
end

function M.get_multiplayer_state()
    return M.multiplayer_state
end

function M.apply_room_event(params)
    if type(params) ~= "table" then
        return
    end
    M.multiplayer_state.enabled = true
    M.multiplayer_state.room = params.room or M.multiplayer_state.room or ""
    M.multiplayer_state.member_count = params.memberCount or 0
    M.multiplayer_state.queue_depth = params.queueDepth or 0
    M.multiplayer_state.active_connection_id = params.activeConnectionId or ""
    M.multiplayer_state.lobby_enabled = params.lobbyEnabled == true
    M.multiplayer_state.preset = params.preset or ""
    M.multiplayer_state.last_event_type = params.eventType or ""
    M.multiplayer_state.members = params.members or {}

    local local_connection_id = M.multiplayer_state.local_connection_id
    if local_connection_id ~= "" and type(M.multiplayer_state.members) == "table" then
        for _, member in ipairs(M.multiplayer_state.members) do
            if type(member) == "table" and member.connectionId == local_connection_id then
                M.multiplayer_state.role = member.role or M.multiplayer_state.role
                break
            end
        end
    end
end

function M.apply_member_role_update(params)
    if type(params) ~= "table" then
        return
    end

    local connection_id = params.connectionId or ""
    local role = params.role or ""
    local members = M.multiplayer_state.members
    if type(members) ~= "table" then
        members = {}
        M.multiplayer_state.members = members
    end

    local updated = false
    for _, member in ipairs(members) do
        if type(member) == "table" and member.connectionId == connection_id then
            member.role = role
            updated = true
            break
        end
    end

    if not updated and connection_id ~= "" then
        table.insert(members, {
            connectionId = connection_id,
            role = role,
        })
    end

    if connection_id ~= "" and connection_id == M.multiplayer_state.local_connection_id then
        M.multiplayer_state.role = role
    end
end

local function restart_delay_ms()
    local initial = config.get("restart_backoff_initial") or 1000
    local max_delay = config.get("restart_backoff_max") or 30000
    local multiplier = config.get("restart_backoff_multiplier") or 2

    local exponent = math.max(M.restart_attempt - 1, 0)
    local delay = initial * (multiplier ^ exponent)
    return math.min(math.floor(delay), max_delay)
end

local function schedule_restart()
    if not config.get("auto_restart") then
        return
    end

    M.restart_attempt = M.restart_attempt + 1
    local delay = restart_delay_ms()

    clear_restart_timer()
    M.restart_timer = vim.defer_fn(function()
        M.restart_timer = nil
        if M.job_id then
            return
        end
        M.start(true)
    end, delay)

    vim.notify(
        "[poor-cli] Server exited unexpectedly, restarting in " .. delay .. "ms",
        vim.log.levels.WARN
    )
end

-- Resolve the command used to start the backend server/bridge.
function M.resolve_server_command()
    local multiplayer = config.get("multiplayer") or {}
    if type(multiplayer) == "table" and multiplayer.enabled then
        local url = multiplayer.url
        local room = multiplayer.room
        local token = multiplayer.token
        if not url or url == "" or not room or room == "" or not token or token == "" then
            return nil, "multiplayer.enabled requires multiplayer.url, multiplayer.room, and multiplayer.token"
        end
        return {
            "poor-cli-server",
            "--bridge",
            "--url",
            url,
            "--room",
            room,
            "--token",
            token,
        }
    end
    return config.get("server_cmd"), nil
end

-- Start the server
function M.start(is_restart)
    if M.job_id then
        vim.notify("[poor-cli] Server already running", vim.log.levels.WARN)
        return M.job_id
    end

    clear_restart_timer()
    M.manual_stop = false
    M.reset_session_state()

    local cmd, err = M.resolve_server_command()
    if not cmd then
        vim.notify("[poor-cli] " .. (err or "Failed to resolve server command"), vim.log.levels.ERROR)
        return nil
    end
    if config.is_debug() then
        vim.notify("[poor-cli] Starting server: " .. vim.inspect(cmd), vim.log.levels.DEBUG)
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

    if not is_restart then
        M.restart_attempt = 0
    end

    vim.notify("[poor-cli] Server started", vim.log.levels.INFO)
    return M.job_id
end

-- Stop the server
function M.stop()
    M.manual_stop = true
    clear_restart_timer()

    if M.job_id then
        vim.fn.jobstop(M.job_id)
        M.job_id = nil
        clear_all_request_timers()
        M.pending = {}
        M.buffer = ""
        M.restart_attempt = 0
        M.reset_session_state()
        vim.notify("[poor-cli] Server stopped", vim.log.levels.INFO)
    else
        M.manual_stop = false
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
    if callback then
        local timeout_ms = config.get("request_timeout") or 15000
        if method == "poor-cli/chatStreaming" then
            timeout_ms = 0
        end
        if timeout_ms > 0 then
            M.pending_timers[id] = vim.defer_fn(function()
                local timed_out_callback = M.pending[id]
                if not timed_out_callback then
                    clear_request_timer(id)
                    return
                end

                M.pending[id] = nil
                clear_request_timer(id)
                timed_out_callback(nil, {
                    code = -32001,
                    message = "Request timed out",
                    data = {
                        request_id = id,
                        method = method,
                        timeout_ms = timeout_ms,
                    },
                })
            end, timeout_ms)
        end
    end
    
    -- Send message
    M.send_message(message)
    
    if config.is_debug() then
        vim.notify("[poor-cli] Request " .. id .. ": " .. method, vim.log.levels.DEBUG)
    end
    
    return id
end

-- Send a JSON-RPC notification (no id, no response expected).
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

-- Cancel an in-flight request by id.
function M.cancel_request(id, err)
    if not id then
        return false
    end

    local callback = M.pending[id]
    M.pending[id] = nil
    clear_request_timer(id)

    if callback and err then
        callback(nil, err)
    end

    return callback ~= nil
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
        clear_request_timer(message.id)
        
        if message.error then
            callback(nil, message.error)
        else
            callback(message.result, nil)
        end
    else
        clear_request_timer(message.id)
    end
end

-- Handle notifications from server
function M.handle_notification(message)
    local params = message.params or {}
    if message.method == "poor-cli/streamChunk" or message.method == "poor-cli/streamingChunk" then
        vim.api.nvim_exec_autocmds("User", {
            pattern = "PoorCliStreamChunk",
            data = {
                request_id = params.requestId or "",
                chunk = params.chunk or params.content or "",
                done = params.done or false,
                reason = params.reason,
            },
        })
    elseif message.method == "poor-cli/toolEvent" then
        vim.api.nvim_exec_autocmds("User", {
            pattern = "PoorCliToolEvent",
            data = {
                request_id = params.requestId or "",
                event_type = params.eventType or "",
                tool_name = params.toolName or "",
                tool_args = params.toolArgs or {},
                tool_result = params.toolResult or "",
                diff = params.diff or "",
                iteration_index = params.iterationIndex or 0,
                iteration_cap = params.iterationCap or 25,
            },
        })
    elseif message.method == "poor-cli/permissionReq" then
        vim.api.nvim_exec_autocmds("User", {
            pattern = "PoorCliPermissionReq",
            data = {
                request_id = params.requestId or "",
                tool_name = params.toolName or "",
                tool_args = params.toolArgs or {},
                prompt_id = params.promptId or "",
            },
        })
    elseif message.method == "poor-cli/planReq" then
        vim.api.nvim_exec_autocmds("User", {
            pattern = "PoorCliPlanReq",
            data = {
                request_id = params.requestId or "",
                prompt_id = params.promptId or "",
                summary = params.summary or "",
                original_request = params.originalRequest or "",
                steps = params.steps or {},
            },
        })
    elseif message.method == "poor-cli/progress" then
        vim.api.nvim_exec_autocmds("User", {
            pattern = "PoorCliProgress",
            data = {
                request_id = params.requestId or "",
                phase = params.phase or "",
                message = params.message or "",
                iteration_index = params.iterationIndex or 0,
                iteration_cap = params.iterationCap or 25,
            },
        })
    elseif message.method == "poor-cli/costUpdate" then
        vim.api.nvim_exec_autocmds("User", {
            pattern = "PoorCliCostUpdate",
            data = {
                request_id = params.requestId or "",
                input_tokens = params.inputTokens or 0,
                output_tokens = params.outputTokens or 0,
                estimated_cost = params.estimatedCost or 0,
            },
        })
    elseif message.method == "poor-cli/roomEvent" then
        M.apply_room_event(params)
        vim.api.nvim_exec_autocmds("User", {
            pattern = "PoorCliRoomEvent",
            data = {
                room = params.room or "",
                event_type = params.eventType or "",
                request_id = params.requestId or "",
                actor = params.actor or "",
                queue_depth = params.queueDepth or 0,
                member_count = params.memberCount or 0,
                active_connection_id = params.activeConnectionId or "",
                lobby_enabled = params.lobbyEnabled or false,
                preset = params.preset or "",
                members = params.members or {},
                details = params.details or {},
            },
        })
    elseif message.method == "poor-cli/memberRoleUpdated" then
        M.apply_member_role_update(params)
        vim.api.nvim_exec_autocmds("User", {
            pattern = "PoorCliMemberRoleUpdated",
            data = {
                room = params.room or "",
                connection_id = params.connectionId or "",
                role = params.role or "",
            },
        })
    elseif message.method == "poor-cli/suggestion" then
        M.multiplayer_state.last_suggestion = {
            sender = params.sender or "",
            text = params.text or "",
            room = params.room or "",
        }
        vim.api.nvim_exec_autocmds("User", {
            pattern = "PoorCliSuggestion",
            data = {
                sender = params.sender or "",
                text = params.text or "",
                room = params.room or "",
            },
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
    local was_manual_stop = M.manual_stop
    M.job_id = nil
    clear_all_request_timers()
    M.pending = {}
    M.buffer = ""
    M.reset_session_state()

    if was_manual_stop then
        M.manual_stop = false
        M.restart_attempt = 0
        if config.is_debug() then
            vim.notify("[poor-cli] Server stopped by user", vim.log.levels.DEBUG)
        end
        return
    end

    if code == 0 then
        M.restart_attempt = 0
        if config.is_debug() then
            vim.notify("[poor-cli] Server exited normally", vim.log.levels.DEBUG)
        end
        return
    end

    if config.get("auto_restart") then
        schedule_restart()
    else
        vim.notify("[poor-cli] Server exited with code " .. code, vim.log.levels.WARN)
    end
end

return M
