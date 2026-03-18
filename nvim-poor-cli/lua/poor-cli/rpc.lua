-- poor-cli/rpc.lua
-- JSON-RPC client for communicating with poor-cli-server

local config = require("poor-cli.config")

local M = {}

M.job_id = nil
M.request_id = 0
M.pending = {}
M.pending_timers = {}
M.pending_meta = {}
M.buffer = ""
M.manual_stop = false
M.restart_attempt = 0
M.restart_timer = nil
M.capabilities = nil
M.server_state = "stopped"
M.last_error = nil
M.last_error_message = ""
M.last_status_message = ""
M.last_request = nil
M.server_log_path = nil
M.last_stderr_excerpt = ""
M.recent_stderr = {}
M.max_stderr_lines = 20
M.multiplayer_state = {
    enabled = false,
    room = "",
    role = "",
    ui_role = "",
    display_name = "",
    approval_state = "",
    hand_raised = false,
    queue_position = 0,
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

local function emit_status_changed()
    vim.api.nvim_exec_autocmds("User", {
        pattern = "PoorCliStatusChanged",
        data = M.get_status(),
    })
end

local function set_last_error(err)
    M.last_error = err
    M.last_error_message = type(err) == "table" and (err.message or vim.inspect(err)) or tostring(err or "")
end

local function current_log_hint()
    if not M.server_log_path or M.server_log_path == "" then
        return ""
    end
    return " Log: " .. M.server_log_path
end

local function notify_with_context(message, level)
    vim.notify("[poor-cli] " .. message .. current_log_hint(), level)
end

local function update_state(state, message)
    M.server_state = state
    if message then
        M.last_status_message = message
    end
    emit_status_changed()
end

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

local function clear_pending_request(id)
    M.pending[id] = nil
    M.pending_meta[id] = nil
    clear_request_timer(id)
end

local function fail_pending_requests(err)
    for id, callback in pairs(M.pending) do
        if callback then
            callback(nil, err)
        end
        clear_pending_request(id)
    end
end

local function fresh_multiplayer_state()
    return {
        enabled = false,
        room = "",
        role = "",
        ui_role = "",
        display_name = "",
        approval_state = "",
        hand_raised = false,
        queue_position = 0,
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

local function append_stderr_line(line)
    if not line or line == "" then
        return
    end

    table.insert(M.recent_stderr, line)
    while #M.recent_stderr > M.max_stderr_lines do
        table.remove(M.recent_stderr, 1)
    end
    M.last_stderr_excerpt = table.concat(M.recent_stderr, "\n")
end

local function request_logical_id(params)
    if type(params) ~= "table" then
        return ""
    end
    return tostring(params.requestId or "")
end

local function build_request_error(message, data)
    local err = {
        code = -32002,
        message = message,
        data = vim.tbl_extend("force", {
            log_path = M.server_log_path,
            stderr_excerpt = M.last_stderr_excerpt,
        }, data or {}),
    }
    set_last_error(err)
    return err
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
    update_state("restarting", "Server restarting")

    clear_restart_timer()
    M.restart_timer = vim.defer_fn(function()
        M.restart_timer = nil
        if M.job_id then
            return
        end
        if M.start(true) then
            M.initialize()
        end
    end, delay)

    notify_with_context(
        "Server exited unexpectedly, restarting in " .. delay .. "ms",
        vim.log.levels.WARN
    )
end

function M.reset_session_state()
    M.capabilities = nil
    M.multiplayer_state = fresh_multiplayer_state()
    M.last_request = nil
end

function M.client_capabilities()
    return {
        uiSurface = "neovim",
        streaming = true,
        completion = {
            partialStreaming = true,
        },
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
        update_state("error", "Initialize returned no capabilities")
        return
    end

    M.capabilities = caps
    local log_path = caps.serverLogPath or caps.logPath
    if type(log_path) == "string" and log_path ~= "" then
        M.server_log_path = log_path
    end

    local multiplayer = caps.multiplayer
    if type(multiplayer) == "table" then
        M.multiplayer_state.enabled = multiplayer.enabled == true
        M.multiplayer_state.room = multiplayer.room or ""
        M.multiplayer_state.role = multiplayer.role or ""
        M.multiplayer_state.ui_role = multiplayer.uiRole or ""
        M.multiplayer_state.display_name = multiplayer.displayName or ""
        M.multiplayer_state.approval_state = multiplayer.approvalState or ""
        M.multiplayer_state.hand_raised = multiplayer.handRaised == true
        M.multiplayer_state.queue_position = multiplayer.queuePosition or 0
        M.multiplayer_state.local_connection_id = multiplayer.connectionId or ""
        M.multiplayer_state.lobby_enabled = multiplayer.lobbyEnabled == true
        M.multiplayer_state.preset = multiplayer.preset or ""
    end

    update_state("ready", "Initialized")
end

function M.get_capabilities()
    return M.capabilities
end

function M.get_multiplayer_state()
    return M.multiplayer_state
end

function M.get_log_path()
    return M.server_log_path or config.get_server_log_file()
end

function M.get_last_stderr_excerpt()
    return M.last_stderr_excerpt
end

function M.get_recent_stderr()
    return vim.deepcopy(M.recent_stderr)
end

function M.get_status()
    local provider_info = nil
    if type(M.capabilities) == "table" then
        provider_info = M.capabilities.providerInfo
    end

    return {
        state = M.server_state,
        running = M.job_id ~= nil,
        initialized = type(M.capabilities) == "table",
        log_path = M.get_log_path(),
        last_error = M.last_error,
        last_error_message = M.last_error_message,
        last_request = M.last_request,
        last_stderr_excerpt = M.last_stderr_excerpt,
        restart_attempt = M.restart_attempt,
        provider_info = provider_info,
        multiplayer = vim.deepcopy(M.multiplayer_state),
        capabilities = M.capabilities,
        status_message = M.last_status_message,
    }
end

function M.build_debug_report(extra_sections)
    local lines = {
        "# poor-cli doctor",
        "",
        "## RPC Status",
        vim.inspect(M.get_status()),
        "",
        "## Plugin Config",
        vim.inspect(config.sanitized_for_debug()),
    }

    if M.last_stderr_excerpt ~= "" then
        table.insert(lines, "")
        table.insert(lines, "## Recent Server STDERR")
        table.insert(lines, M.last_stderr_excerpt)
    end

    if type(extra_sections) == "table" then
        for _, section in ipairs(extra_sections) do
            if type(section) == "table" and section.title and section.body then
                table.insert(lines, "")
                table.insert(lines, "## " .. section.title)
                table.insert(lines, tostring(section.body))
            end
        end
    end

    return table.concat(lines, "\n")
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
                M.multiplayer_state.ui_role = member.uiRole or M.multiplayer_state.ui_role
                M.multiplayer_state.display_name = member.displayName or M.multiplayer_state.display_name
                M.multiplayer_state.approval_state = member.approvalState or M.multiplayer_state.approval_state
                M.multiplayer_state.hand_raised = member.handRaised == true
                M.multiplayer_state.queue_position = tonumber(member.queuePosition) or 0
                break
            end
        end
    end
    emit_status_changed()
end

function M.apply_member_role_update(params)
    if type(params) ~= "table" then
        return
    end

    local connection_id = params.connectionId or ""
    local role = params.role or ""
    local ui_role = params.uiRole or ""
    local members = M.multiplayer_state.members
    if type(members) ~= "table" then
        members = {}
        M.multiplayer_state.members = members
    end

    local updated = false
    for _, member in ipairs(members) do
        if type(member) == "table" and member.connectionId == connection_id then
            member.role = role
            member.uiRole = ui_role
            updated = true
            break
        end
    end

    if not updated and connection_id ~= "" then
        table.insert(members, {
            connectionId = connection_id,
            role = role,
            uiRole = ui_role,
        })
    end

    if connection_id ~= "" and connection_id == M.multiplayer_state.local_connection_id then
        M.multiplayer_state.role = role
        if ui_role ~= "" then
            M.multiplayer_state.ui_role = ui_role
        end
    end
    emit_status_changed()
end

function M.resolve_server_command()
    local multiplayer = config.get("multiplayer") or {}
    if type(multiplayer) == "table" and multiplayer.enabled then
        local invite = multiplayer.invite
        if invite and invite ~= "" then
            return {
                "poor-cli-server",
                "--bridge",
                "--invite",
                invite,
            }, nil
        end
        local url = multiplayer.url
        local room = multiplayer.room
        local token = multiplayer.token
        if not url or url == "" or not room or room == "" or not token or token == "" then
            return nil, "multiplayer.enabled requires multiplayer.invite or multiplayer.url, multiplayer.room, and multiplayer.token"
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
        }, nil
    end
    return config.get("server_cmd"), nil
end

function M.start(is_restart)
    if M.job_id then
        notify_with_context("Server already running", vim.log.levels.WARN)
        return M.job_id
    end

    clear_restart_timer()
    M.manual_stop = false
    M.reset_session_state()
    M.server_log_path = config.get_server_log_file()

    local cmd, err = M.resolve_server_command()
    if not cmd then
        set_last_error(err or "Failed to resolve server command")
        update_state("error", "Server start failed")
        notify_with_context(err or "Failed to resolve server command", vim.log.levels.ERROR)
        return nil
    end
    if config.is_debug() then
        vim.notify("[poor-cli] Starting server: " .. vim.inspect(cmd), vim.log.levels.DEBUG)
    end

    update_state(is_restart and "restarting" or "starting", "Starting server")

    M.job_id = vim.fn.jobstart(cmd, {
        env = {
            POOR_CLI_SERVER_LOG_FILE = M.server_log_path,
        },
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
        M.job_id = nil
        set_last_error("Failed to start server")
        update_state("error", "Server start failed")
        notify_with_context("Failed to start server", vim.log.levels.ERROR)
        return nil
    end

    if not is_restart then
        M.restart_attempt = 0
    end

    notify_with_context("Server started", vim.log.levels.INFO)
    return M.job_id
end

function M.initialize(callback, opts)
    if not M.job_id then
        local err = build_request_error("Server not running", {})
        if callback then
            callback(nil, err)
        end
        return nil
    end

    update_state("initializing", "Initializing")

    return M.request("initialize", {
        provider = (opts and opts.provider) or config.get("provider"),
        model = (opts and opts.model) or config.get("model"),
        streaming = true,
        clientCapabilities = M.client_capabilities(),
    }, function(result, err)
        if err then
            set_last_error(err)
            update_state("error", "Initialization failed")
            notify_with_context("Init failed: " .. vim.inspect(err), vim.log.levels.ERROR)
        else
            M.capture_initialize_result(result)
            if config.is_debug() then
                vim.notify("[poor-cli] Initialized: " .. vim.inspect(result), vim.log.levels.DEBUG)
            end
        end
        if callback then
            callback(result, err)
        end
    end)
end

function M.restart(callback)
    M.stop()
    if not M.start(false) then
        if callback then
            callback(nil, build_request_error("Failed to restart server", {}))
        end
        return nil
    end
    return M.initialize(callback)
end

function M.restart_with_bootstrap(bootstrap, callback)
    if type(bootstrap) ~= "table" then
        config.clear_multiplayer_bootstrap()
    else
        config.set_multiplayer_bootstrap(bootstrap)
    end
    return M.restart(callback)
end

function M.stop()
    M.manual_stop = true
    clear_restart_timer()

    if M.job_id then
        local stop_error = build_request_error("Server stopped", {
            request_id = "",
        })
        fail_pending_requests(stop_error)
        vim.fn.jobstop(M.job_id)
        M.job_id = nil
        M.buffer = ""
        M.restart_attempt = 0
        M.reset_session_state()
        update_state("stopped", "Stopped")
        notify_with_context("Server stopped", vim.log.levels.INFO)
    else
        M.manual_stop = false
        update_state("stopped", "Stopped")
    end
end

function M.is_running()
    return M.job_id ~= nil
end

function M.request(method, params, callback)
    if not M.job_id then
        local err = build_request_error("Server not running", {
            method = method,
        })
        if callback then
            callback(nil, err)
        end
        return nil
    end

    M.request_id = M.request_id + 1
    local id = M.request_id
    local logical_request_id = request_logical_id(params)

    local message = {
        jsonrpc = "2.0",
        id = id,
        method = method,
        params = params or {},
    }

    M.pending[id] = callback
    M.pending_meta[id] = {
        method = method,
        request_id = logical_request_id,
        started_at = os.time(),
    }

    if callback then
        local timeout_ms = config.get("request_timeout") or 15000
        if method == "poor-cli/chatStreaming" then
            timeout_ms = 0
        end
        if timeout_ms > 0 then
            M.pending_timers[id] = vim.defer_fn(function()
                local timed_out_callback = M.pending[id]
                local meta = M.pending_meta[id] or {}
                if not timed_out_callback then
                    clear_request_timer(id)
                    return
                end

                clear_pending_request(id)
                local err = build_request_error("Request timed out", {
                    rpc_request_id = id,
                    request_id = meta.request_id or "",
                    method = method,
                    timeout_ms = timeout_ms,
                })
                timed_out_callback(nil, err)
                emit_status_changed()
            end, timeout_ms)
        end
    end

    M.send_message(message)

    if config.is_debug() then
        vim.notify("[poor-cli] Request " .. id .. ": " .. method, vim.log.levels.DEBUG)
    end

    return id
end

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

function M.start_collab(opts, callback)
    return M.request("poor-cli/startHostServer", opts or {}, callback)
end

function M.get_collab_status(callback)
    return M.request("poor-cli/getHostServerStatus", {}, callback)
end

function M.leave_collab(callback)
    return M.restart_with_bootstrap({
        enabled = false,
    }, callback)
end

function M.pass_driver(target, callback)
    local params = {}
    if target and target ~= "" then
        params.connectionId = target
    end
    local room = M.multiplayer_state.room or ""
    if room ~= "" then
        params.room = room
    end
    return M.request("poor-cli/passDriver", params, callback)
end

function M.suggest_text(text, callback)
    local params = {
        text = text,
    }
    local room = M.multiplayer_state.room or ""
    if room ~= "" then
        params.room = room
    end
    return M.request("poor-cli/suggestText", params, callback)
end

function M.list_joined_room_members(room, callback)
    local params = {}
    if room and room ~= "" then
        params.room = room
    elseif M.multiplayer_state.room ~= "" then
        params.room = M.multiplayer_state.room
    end
    return M.request("poor-cli/listRoomMembers", params, callback)
end

function M.list_host_room_members(room, callback)
    local params = {}
    if room and room ~= "" then
        params.room = room
    end
    return M.request("poor-cli/listHostMembers", params, callback)
end

function M.cancel_request(id, err)
    if not id then
        return false
    end

    local callback = M.pending[id]
    local meta = M.pending_meta[id] or {}
    clear_pending_request(id)

    if M.job_id and meta.request_id ~= "" then
        M.request("poor-cli/cancelRequest", {
            requestId = meta.request_id,
        }, nil)
    end

    if callback and err then
        callback(nil, err)
    end

    emit_status_changed()
    return callback ~= nil or meta.request_id ~= ""
end

function M.send_message(message)
    local json = vim.fn.json_encode(message)
    local content = "Content-Length: " .. #json .. "\r\n\r\n" .. json
    local sent = vim.fn.chansend(M.job_id, content)
    if sent == 0 then
        local err = build_request_error("Failed to send message to poor-cli-server", {})
        notify_with_context(err.message, vim.log.levels.ERROR)
    end
end

function M.handle_stdout(data)
    for _, chunk in ipairs(data) do
        M.buffer = M.buffer .. chunk
    end

    while true do
        local message = M.parse_message()
        if not message then
            break
        end
        M.handle_response(message)
    end
end

function M.parse_message()
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
        return nil
    end

    local body = M.buffer:sub(body_start, body_end)
    M.buffer = M.buffer:sub(body_end + 1)

    local ok, message = pcall(vim.fn.json_decode, body)
    if not ok then
        local err = build_request_error("Failed to parse JSON response", {
            body = body,
        })
        notify_with_context(err.message, vim.log.levels.ERROR)
        return nil
    end

    return message
end

function M.handle_response(message)
    if config.is_debug() then
        vim.notify("[poor-cli] Response: " .. vim.inspect(message), vim.log.levels.DEBUG)
    end

    if not message.id then
        M.handle_notification(message)
        return
    end

    local callback = M.pending[message.id]
    local meta = M.pending_meta[message.id]
    if meta then
        M.last_request = vim.deepcopy(meta)
    end

    clear_pending_request(message.id)

    if callback then
        if message.error then
            set_last_error(message.error)
            callback(nil, message.error)
        else
            callback(message.result, nil)
        end
    end

    emit_status_changed()
end

function M.handle_notification(message)
    local params = message.params or {}
    if message.method == "poor-cli/thinkingChunk" then
        vim.api.nvim_exec_autocmds("User", {
            pattern = "PoorCliThinkingChunk",
            data = {
                request_id = params.requestId or "",
                chunk = params.chunk or "",
            },
        })
    elseif message.method == "poor-cli/streamChunk" or message.method == "poor-cli/streamingChunk" then
        vim.api.nvim_exec_autocmds("User", {
            pattern = "PoorCliStreamChunk",
            data = {
                request_id = params.requestId or "",
                chunk = params.chunk or params.content or "",
                done = params.done or false,
                reason = params.reason,
            },
        })
    elseif message.method == "poor-cli/inlineChunk" then
        vim.api.nvim_exec_autocmds("User", {
            pattern = "PoorCliInlineChunk",
            data = {
                request_id = params.requestId or "",
                chunk = params.chunk or "",
                done = params.done or false,
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

function M.handle_stderr(data)
    for _, line in ipairs(data) do
        if line ~= "" then
            append_stderr_line(line)
            if config.is_debug() then
                vim.notify("[poor-cli server] " .. line, vim.log.levels.DEBUG)
            end
        end
    end
    emit_status_changed()
end

function M.handle_exit(code)
    local was_manual_stop = M.manual_stop
    local exit_error = build_request_error("Server exited with code " .. tostring(code), {
        exit_code = code,
    })

    M.job_id = nil
    fail_pending_requests(exit_error)
    M.buffer = ""
    M.reset_session_state()

    if was_manual_stop then
        M.manual_stop = false
        M.restart_attempt = 0
        update_state("stopped", "Stopped")
        if config.is_debug() then
            vim.notify("[poor-cli] Server stopped by user", vim.log.levels.DEBUG)
        end
        return
    end

    if code == 0 then
        M.restart_attempt = 0
        update_state("stopped", "Stopped")
        if config.is_debug() then
            vim.notify("[poor-cli] Server exited normally", vim.log.levels.DEBUG)
        end
        return
    end

    if config.get("auto_restart") then
        schedule_restart()
    else
        update_state("error", "Server exited unexpectedly")
        notify_with_context("Server exited with code " .. code, vim.log.levels.WARN)
    end
end

return M
