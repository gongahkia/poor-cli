-- poor-cli/rpc.lua
-- JSON-RPC client for communicating with poor-cli-server

local config = require("poor-cli.config")

local M = {}

function M.format_error(err)
    if type(err) == "table" then return err.message or err.data or vim.inspect(err) end
    return tostring(err or "unknown error")
end

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
M.startup_feedback = {
    timer = nil,
    frame = 1,
    echo_id = nil,
    started_ns = 0,
    active = false,
    can_replace = nil,
    last_message = "",
}
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
local uv = vim.uv or vim.loop
local spinner_frames = { "-", "\\", "|", "/" }
local startup_states = {
    starting = true,
    initializing = true,
    restarting = true,
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

local function latest_stderr_line()
    for idx = #M.recent_stderr, 1, -1 do
        local line = M.recent_stderr[idx]
        if line and line ~= "" then
            return line
        end
    end
    return ""
end

local function truncate_line(text, max_len)
    local content = tostring(text or "")
    if #content <= max_len then
        return content
    end
    return content:sub(1, math.max(max_len - 3, 1)) .. "..."
end

local function startup_elapsed_seconds()
    if M.startup_feedback.started_ns <= 0 or not uv or not uv.hrtime then
        return 0
    end
    return math.max(0, math.floor((uv.hrtime() - M.startup_feedback.started_ns) / 1000000000))
end

local function startup_phase_text(state)
    if state == "starting" then
        return "starting server"
    end
    if state == "initializing" then
        return "initializing session"
    end
    if state == "restarting" then
        return "restarting server"
    end
    return tostring(state or "starting")
end

local function echo_startup_line(message, is_error)
    local chunks = { { message, is_error and "ErrorMsg" or "ModeMsg" } }

    if M.startup_feedback.can_replace == false then
        if M.startup_feedback.last_message == message then
            return
        end
        pcall(vim.api.nvim_echo, chunks, false, { err = is_error == true })
        M.startup_feedback.last_message = message
        return
    end

    local opts = { err = is_error == true }
    if M.startup_feedback.echo_id and M.startup_feedback.echo_id > 0 then
        opts.id = M.startup_feedback.echo_id
    end
    local ok, id = pcall(vim.api.nvim_echo, chunks, false, opts)
    if ok and type(id) == "number" and id > 0 then
        M.startup_feedback.can_replace = true
        M.startup_feedback.echo_id = id
        M.startup_feedback.last_message = message
        return
    end

    M.startup_feedback.can_replace = false
    pcall(vim.api.nvim_echo, chunks, false, { err = is_error == true })
    M.startup_feedback.last_message = message
end

local function render_startup_feedback()
    if not M.startup_feedback.active then
        return
    end

    local state = M.server_state or "starting"
    local frame = "."
    if M.startup_feedback.can_replace ~= false then
        frame = spinner_frames[M.startup_feedback.frame]
        M.startup_feedback.frame = (M.startup_feedback.frame % #spinner_frames) + 1
    end

    local message = string.format(
        "[poor-cli] [%s] %s (%ds)",
        frame,
        startup_phase_text(state),
        startup_elapsed_seconds()
    )
    if M.last_status_message and M.last_status_message ~= "" and M.last_status_message ~= "Starting server" then
        message = message .. " | " .. truncate_line(M.last_status_message, 72)
    end

    local stderr_line = latest_stderr_line()
    if stderr_line ~= "" and (state == "restarting" or state == "error") then
        message = message .. " | " .. truncate_line(stderr_line, 96)
    end

    echo_startup_line(message, state == "error")
end

local function stop_startup_feedback(state)
    if not M.startup_feedback.active and not M.startup_feedback.timer then
        return
    end

    M.startup_feedback.active = false
    if M.startup_feedback.timer then
        local timer = M.startup_feedback.timer
        M.startup_feedback.timer = nil
        pcall(function()
            timer:stop()
            timer:close()
        end)
    end

    local elapsed = startup_elapsed_seconds()
    if state == "ready" then
        echo_startup_line(string.format("[poor-cli] [ok] initialized in %ds", elapsed), false)
        -- follow-up: probe provider info to confirm config is fully loaded and responsive
        local config_probe_start = (uv and uv.hrtime and uv.hrtime()) or 0
        M.request("poor-cli/getProviderInfo", {}, function(result, err)
            vim.schedule(function()
                if err then return end -- soft-init or transient failure; stay silent
                local probe_elapsed = 0
                if config_probe_start > 0 and uv and uv.hrtime then
                    probe_elapsed = math.max(0, math.floor((uv.hrtime() - config_probe_start) / 1000000000))
                end
                local provider_name = (result and result.name) or "unknown"
                if provider_name == "unconfigured" then return end -- soft-init stub, skip
                pcall(vim.api.nvim_echo, {{
                    string.format("[poor-cli] [ok] configuration loaded in %ds ✓ (%s)", probe_elapsed, provider_name),
                    "MoreMsg",
                }}, false, {})
            end)
        end)
    elseif state == "error" then
        echo_startup_line(string.format("[poor-cli] [error] startup failed after %ds", elapsed), true)
    end

    M.startup_feedback.started_ns = 0
    M.startup_feedback.frame = 1
    M.startup_feedback.echo_id = nil
    M.startup_feedback.can_replace = nil
    M.startup_feedback.last_message = ""
end

local function ensure_startup_feedback()
    if M.startup_feedback.active then
        return
    end

    M.startup_feedback.active = true
    M.startup_feedback.frame = 1
    M.startup_feedback.started_ns = (uv and uv.hrtime and uv.hrtime()) or 0
    M.startup_feedback.can_replace = nil
    M.startup_feedback.last_message = ""

    if uv and uv.new_timer then
        M.startup_feedback.timer = uv.new_timer()
        if M.startup_feedback.timer then
            M.startup_feedback.timer:start(0, 120, vim.schedule_wrap(function()
                render_startup_feedback()
            end))
        end
    end

    render_startup_feedback()
end

local function update_state(state, message)
    M.server_state = state
    if message then
        M.last_status_message = message
    end
    if startup_states[state] then
        ensure_startup_feedback()
        render_startup_feedback()
    else
        stop_startup_feedback(state)
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
        if not invite or invite == "" then
            return nil, "multiplayer.enabled requires multiplayer.invite"
        end
        return {
            "poor-cli-server",
            "--bridge",
            "--invite",
            invite,
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
            notify_with_context("Init failed: " .. M.format_error(err), vim.log.levels.ERROR)
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
        elseif method == "poor-cli/testApiKey" then
            timeout_ms = 45000 -- validation hits remote provider, needs headroom over backend's urlopen timeout
        elseif method == "initialize" then
            timeout_ms = 120000 -- server init runs repo indexing, provider probe, etc.
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

function M.request_sync(method, params, timeout_ms)
    local completed = false
    local result = nil
    local err = nil
    local effective_timeout = timeout_ms or config.get("request_timeout") or 15000

    local request_id = M.request(method, params or {}, function(res, rpc_err)
        result = res
        err = rpc_err
        completed = true
    end)

    if request_id == nil and not completed then
        return nil, build_request_error("Request failed to start", {
            method = method,
        })
    end

    if completed then
        return result, err
    end

    local ok = vim.wait(effective_timeout, function()
        return completed
    end, 20)

    if not ok then
        return nil, build_request_error("Synchronous request timed out", {
            method = method,
            timeout_ms = effective_timeout,
        })
    end

    return result, err
end

function M.get_status_view(timeout_ms)
    return M.request_sync("poor-cli/getStatusView", {}, timeout_ms)
end

function M.get_trust_view(timeout_ms)
    return M.request_sync("poor-cli/getTrustView", {}, timeout_ms)
end

function M.get_doctor_report(timeout_ms)
    return M.request_sync("poor-cli/getDoctorReport", {}, timeout_ms)
end

function M.get_context_explain(params, timeout_ms)
    return M.request_sync("poor-cli/getContextExplain", params or {}, timeout_ms)
end

function M.list_runs(params, timeout_ms)
    return M.request_sync("poor-cli/listRuns", params or {}, timeout_ms)
end

function M.list_workflows(timeout_ms)
    return M.request_sync("poor-cli/listWorkflows", {}, timeout_ms)
end

function M.get_workflow(name, timeout_ms)
    return M.request_sync("poor-cli/getWorkflow", {
        name = name,
    }, timeout_ms)
end

-- search / indexing
function M.semantic_search(query, limit, callback)
    return M.request("poor-cli/semanticSearch", { query = query, limit = limit or 10 }, callback)
end
function M.vector_search(query, limit, callback)
    return M.request("poor-cli/vectorSearch", { query = query, limit = limit or 10 }, callback)
end
function M.hybrid_search(query, limit, callback)
    return M.request("poor-cli/hybridSearch", { query = query, limit = limit or 10 }, callback)
end
function M.index_codebase(callback)
    return M.request("poor-cli/indexCodebase", {}, callback)
end
function M.get_index_stats(timeout_ms)
    return M.request_sync("poor-cli/getIndexStats", {}, timeout_ms)
end
-- service management
function M.start_service(name, command, callback)
    return M.request("poor-cli/startService", { name = name, command = command }, callback)
end
function M.stop_service(name, callback)
    return M.request("poor-cli/stopService", { name = name }, callback)
end
function M.get_service_status(name, timeout_ms)
    return M.request_sync("poor-cli/getServiceStatus", { name = name }, timeout_ms)
end
function M.get_service_logs(name, tail, timeout_ms)
    return M.request_sync("poor-cli/getServiceLogs", { name = name, tail = tail or 50 }, timeout_ms)
end
-- mcp
function M.get_mcp_status(timeout_ms)
    return M.request_sync("poor-cli/getMcpStatus", {}, timeout_ms)
end
function M.mcp_health_check(callback)
    return M.request("poor-cli/mcpHealthCheck", {}, callback)
end
-- policy
function M.get_policy_status(timeout_ms)
    return M.request_sync("poor-cli/getPolicyStatus", {}, timeout_ms)
end
-- workspace file search
function M.search_workspace_files(query, limit, callback)
    return M.request("poor-cli/searchWorkspaceFiles", { query = query, limit = limit or 20 }, callback)
end
-- compare files
function M.compare_files(file1, file2, timeout_ms)
    return M.request_sync("poor-cli/compareFiles", { file1 = file1, file2 = file2 }, timeout_ms)
end
-- host server standalone
function M.start_host_server(opts, callback)
    return M.request("poor-cli/startHostServer", opts or {}, callback)
end
function M.stop_host_server(callback)
    return M.request("poor-cli/stopHostServer", {}, callback)
end
function M.get_host_server_status(timeout_ms)
    return M.request_sync("poor-cli/getHostServerStatus", {}, timeout_ms)
end

function M.get_collab_summary(timeout_ms)
    return M.request_sync("poor-cli/getCollabSummary", {}, timeout_ms)
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

-- deploy
function M.deploy_targets(callback) return M.request("poor-cli/deployTargets", {}, callback) end
function M.deploy_validate(callback) return M.request("poor-cli/deployValidate", {}, callback) end
function M.deploy_history(params, callback) return M.request("poor-cli/deployHistory", params or {}, callback) end
-- preview
function M.preview_start(params, callback) return M.request("poor-cli/previewStart", params or {}, callback) end
function M.preview_stop(callback) return M.request("poor-cli/previewStop", {}, callback) end
function M.preview_status(timeout_ms) return M.request_sync("poor-cli/previewStatus", {}, timeout_ms) end
-- sandbox diagnostics
function M.sandbox_status(timeout_ms) return M.request_sync("poor-cli/getSandboxStatus", {}, timeout_ms) end
function M.docker_sandbox_status(timeout_ms) return M.request_sync("poor-cli/getDockerSandboxStatus", {}, timeout_ms) end
-- sessions / embeddings
function M.list_sessions_all(params, callback) return M.request("poor-cli/listSessions", params or {}, callback) end
function M.index_embeddings(params, callback) return M.request("poor-cli/indexEmbeddings", params or {}, callback) end
-- providers
function M.list_providers(timeout_ms) return M.request_sync("poor-cli/listProviders", {}, timeout_ms) end
-- permissions
function M.get_permissions(timeout_ms) return M.request_sync("poor-cli/getPermissions", {}, timeout_ms) end
function M.set_permissions(params, callback) return M.request("poor-cli/setPermissions", params or {}, callback) end
-- cost estimation
function M.estimate_cost(params, timeout_ms) return M.request_sync("poor-cli/estimateCost", params or {}, timeout_ms) end
-- export
function M.export_conversation(params, callback) return M.request("poor-cli/exportConversation", params or {}, callback) end
-- deploy execution
function M.deploy(params, callback) return M.request("poor-cli/deploy", params or {}, callback) end
-- mutation preview
function M.preview_mutation(params, timeout_ms) return M.request_sync("poor-cli/previewMutation", params or {}, timeout_ms) end
-- file watcher
function M.watch_scan(callback) return M.request("poor-cli/watchScan", {}, callback) end
-- profiles
function M.list_profiles(timeout_ms) return M.request_sync("poor-cli/listProfiles", {}, timeout_ms) end
function M.apply_profile(params, callback) return M.request("poor-cli/applyProfile", params or {}, callback) end
-- trust management
function M.get_trust_status(timeout_ms) return M.request_sync("poor-cli/getTrustStatus", {}, timeout_ms) end
function M.trust_repo(params, callback) return M.request("poor-cli/trustRepo", params or {}, callback) end
function M.untrust_repo(params, callback) return M.request("poor-cli/untrustRepo", params or {}, callback) end
-- ollama
function M.list_ollama_models(timeout_ms) return M.request_sync("poor-cli/listOllamaModels", {}, timeout_ms) end
-- status view
function M.get_status_view(timeout_ms) return M.request_sync("poor-cli/getStatusView", {}, timeout_ms) end

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
    -- Neovim's on_stdout splits on "\n" and strips them. Re-insert \n between
    -- chunks so the \r\n\r\n header/body separator survives reassembly.
    for i, chunk in ipairs(data) do
        M.buffer = M.buffer .. chunk
        if i < #data then
            M.buffer = M.buffer .. "\n"
        end
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
                cache_creation_input_tokens = params.cacheCreationInputTokens or 0,
                cache_read_input_tokens = params.cacheReadInputTokens or 0,
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
    if M.startup_feedback.active then
        render_startup_feedback()
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
        vim.notify("[poor-cli] Server restarted — chat context was reset. Use :PoorCliSessionRestore to recover.", vim.log.levels.WARN)
        schedule_restart()
    else
        update_state("error", "Server exited unexpectedly")
        notify_with_context("Server exited with code " .. code .. ". Run :PoorCliDoctor for diagnostics.", vim.log.levels.WARN)
    end
end

return M
