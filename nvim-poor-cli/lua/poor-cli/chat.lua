-- poor-cli/chat.lua
-- Chat panel for AI conversations

local config = require("poor-cli.config")
local rpc = require("poor-cli.rpc")
local diagnostics = require("poor-cli.diagnostics")

local M = {}

M.buf = nil
M.win = nil
M.history = {}
M.input_buf = nil
M.input_win = nil
M.loading_ns = vim.api.nvim_create_namespace("poor-cli-chat-loading")
M.loading_marker = nil
M.streaming_buf_line = nil
M.streaming_request_id = nil
M.streaming_response_text = nil
M.active_stream = nil -- { request_id, rpc_request_id }
M.message_queue = {} -- FIFO queue of { message = string, resolved_msg = string, mention_files = {}, context_files = {} }
M.stream_meta = nil -- { started_at_ns, input_tokens, output_tokens, estimated_cost, cache_read, cache_creation }

local function is_active_request(request_id)
    return M.active_stream and M.active_stream.request_id ~= "" and M.active_stream.request_id == request_id
end

local function emit_debug_note(lines)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    -- only surface per-chunk cost/progress noise when debug mode is on
    local ok, cfg = pcall(require, "poor-cli.config")
    if not ok or not cfg.is_debug or not cfg.is_debug() then
        return
    end
    local line_count = vim.api.nvim_buf_line_count(M.buf)
    vim.api.nvim_buf_set_lines(M.buf, line_count, line_count, false, lines)
end

local function scan_workspace_files(root, depth, results)
    results = results or {}
    depth = depth or 0
    if depth > 3 or #results >= 50 then
        return results
    end

    local handle = vim.loop.fs_scandir(root)
    if not handle then
        return results
    end

    while #results < 50 do
        local name, entry_type = vim.loop.fs_scandir_next(handle)
        if not name then
            break
        end

        if name ~= ".git" and name ~= "node_modules" and name ~= "__pycache__" and name ~= "target" then
            local path = vim.fs.joinpath(root, name)
            if entry_type == "file" then
                table.insert(results, path)
            elseif entry_type == "directory" then
                scan_workspace_files(path, depth + 1, results)
            end
        end
    end

    return results
end

function M.open()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_set_current_win(M.win)
        return
    end

    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        M.buf = vim.api.nvim_create_buf(false, true)
        vim.bo[M.buf].buftype = "nofile"
        vim.bo[M.buf].bufhidden = "hide"
        vim.bo[M.buf].swapfile = false
        vim.bo[M.buf].filetype = "markdown"
        vim.api.nvim_buf_set_name(M.buf, "[poor-cli chat]")
        vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, {
            "# poor-cli Chat",
            "",
            "Use `:PoorCliSend` or press `<CR>` at the bottom to send a message.",
            "",
            "---",
            "",
        })
    end

    local width = config.get("chat_width")
    local position = config.get("chat_position")
    if position == "right" then
        vim.cmd("botright " .. width .. "vsplit")
    else
        vim.cmd("topleft " .. width .. "vsplit")
    end

    M.win = vim.api.nvim_get_current_win()
    vim.api.nvim_win_set_buf(M.win, M.buf)
    vim.wo[M.win].wrap = true
    vim.wo[M.win].linebreak = true
    vim.wo[M.win].number = false
    vim.wo[M.win].relativenumber = false
    vim.wo[M.win].signcolumn = "no"
    vim.cmd("normal! G")
    M.setup_buffer_keymaps()
end

function M.close()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_win_close(M.win, true)
        M.win = nil
    end
end

function M.toggle()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        M.close()
    else
        M.open()
    end
end

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
    for _, line in ipairs(vim.split(content, "\n", { plain = true })) do
        table.insert(lines, line)
    end
    table.insert(lines, "")
    table.insert(lines, "---")
    table.insert(lines, "")

    local line_count = vim.api.nvim_buf_line_count(M.buf)
    vim.api.nvim_buf_set_lines(M.buf, line_count, line_count, false, lines)

    if M.win and vim.api.nvim_win_is_valid(M.win) then
        local new_count = vim.api.nvim_buf_line_count(M.buf)
        vim.api.nvim_win_set_cursor(M.win, { new_count, 0 })
    end

    table.insert(M.history, { role = role, content = content })
    if role == "assistant" then
        diagnostics.apply_from_text(content)
    end
end

-- System status bar: a small floating window anchored at the bottom of the
-- chat split.  Notes auto-dismiss after a few seconds so they don't clutter
-- the conversation history.

M._status_bar = { buf = nil, win = nil, timer = nil }

local function status_bar_close()
    local sb = M._status_bar
    if sb.timer then
        pcall(function() sb.timer:stop(); sb.timer:close() end)
        sb.timer = nil
    end
    if sb.win and vim.api.nvim_win_is_valid(sb.win) then
        vim.api.nvim_win_close(sb.win, true)
    end
    sb.win = nil
    if sb.buf and vim.api.nvim_buf_is_valid(sb.buf) then
        vim.api.nvim_buf_delete(sb.buf, { force = true })
    end
    sb.buf = nil
end

function M.append_system_note(content, opts)
    opts = opts or {}
    local timeout_ms = opts.timeout or 5000

    if not M.win or not vim.api.nvim_win_is_valid(M.win) then
        -- fallback: no chat window open, use vim.notify
        vim.notify("[poor-cli] " .. content, vim.log.levels.INFO)
        return
    end

    status_bar_close()

    local sb = M._status_bar
    sb.buf = vim.api.nvim_create_buf(false, true)
    vim.bo[sb.buf].buftype = "nofile"
    vim.bo[sb.buf].bufhidden = "wipe"
    vim.bo[sb.buf].swapfile = false

    -- format content lines with padding
    local text_lines = vim.split(content, "\n", { plain = true })
    local display = {}
    for _, line in ipairs(text_lines) do
        table.insert(display, " ℹ️  " .. line .. " ")
    end

    vim.api.nvim_buf_set_lines(sb.buf, 0, -1, false, display)

    -- compute dimensions relative to chat window
    local chat_width = vim.api.nvim_win_get_width(M.win)
    local chat_height = vim.api.nvim_win_get_height(M.win)
    local bar_width = math.min(chat_width - 2, 60)
    local bar_height = #display

    -- anchor to bottom-center of the chat window
    local chat_pos = vim.api.nvim_win_get_position(M.win)
    local row = chat_pos[1] + chat_height - bar_height - 1
    local col = chat_pos[2] + math.max(0, math.floor((chat_width - bar_width) / 2))

    sb.win = vim.api.nvim_open_win(sb.buf, false, {
        relative = "editor",
        width = bar_width,
        height = bar_height,
        row = math.max(0, row),
        col = col,
        style = "minimal",
        border = "single",
        focusable = false,
        zindex = 50,
    })

    -- dim styling
    if sb.win and vim.api.nvim_win_is_valid(sb.win) then
        vim.wo[sb.win].winblend = 15
    end

    -- auto-dismiss
    if timeout_ms > 0 and vim.loop.new_timer then
        sb.timer = vim.loop.new_timer()
        sb.timer:start(timeout_ms, 0, vim.schedule_wrap(function()
            status_bar_close()
        end))
    end
end

function M._resolve_mentions(message)
    local extra_files = {}
    local resolved = message:gsub("@file:([%w%._/%-~]+)", function(path)
        local abs = vim.fn.fnamemodify(path, ":p")
        if vim.fn.filereadable(abs) == 1 then
            table.insert(extra_files, abs)
            local lines = vim.fn.readfile(abs)
            local content = table.concat(lines, "\n")
            local lang = vim.filetype.match({ filename = abs }) or ""
            return "```" .. lang .. "\n-- " .. path .. "\n" .. content .. "\n```"
        end
        return "@file:" .. path
    end)

    resolved = resolved:gsub("@workspace", function()
        local cwd = vim.fn.getcwd()
        local files = scan_workspace_files(cwd, 0, {})
        if #files == 0 then
            return "@workspace"
        end
        return "```\n-- Project files:\n" .. table.concat(files, "\n") .. "\n```"
    end)

    return resolved, extra_files
end

function M.cancel_active_stream(reason)
    if not M.active_stream then
        return false
    end

    local active = vim.deepcopy(M.active_stream)
    M._stop_thinking_timer()
    M._streaming_placeholder_active = false
    M.active_stream = nil
    M.streaming_request_id = nil
    M.streaming_response_text = nil
    M.streaming_buf_line = nil
    M.stream_meta = nil
    if active.rpc_request_id then
        rpc.cancel_request(active.rpc_request_id, {
            code = -32800,
            message = reason or "Request cancelled",
            data = {
                request_id = active.request_id,
            },
        })
    end
    if reason then
        M.append_system_note(reason)
    end

    -- finalize the visual block (add separator) then drain queue
    if M.buf and vim.api.nvim_buf_is_valid(M.buf) then
        local line_count = vim.api.nvim_buf_line_count(M.buf)
        vim.api.nvim_buf_set_lines(M.buf, line_count, line_count, false, { "", "---", "" })
    end
    vim.schedule(function()
        M._process_queue()
    end)

    return true
end

-- Prepare a message for sending: resolve mentions, inject diagnostics, gather context.
-- Returns a table suitable for queuing or immediate dispatch.
local function prepare_message(message)
    local resolved_msg, mention_files = M._resolve_mentions(message)

    local error_keywords = { "error", "warning", "issue", "bug", "fix", "broken", "fail", "diagnostic" }
    local lower_msg = message:lower()
    for _, kw in ipairs(error_keywords) do
        if lower_msg:find(kw, 1, true) then
            local diag_ctx = diagnostics.get_workspace_diagnostics_summary()
            if diag_ctx then
                resolved_msg = resolved_msg .. "\n\n" .. diag_ctx
            end
            break
        end
    end

    local context_files = M.get_context_files()
    for _, file_path in ipairs(mention_files) do
        table.insert(context_files, file_path)
    end

    return {
        message = message,
        resolved_msg = resolved_msg,
        context_files = context_files,
    }
end

-- Dispatch a prepared message to the server (no queue check — caller ensures
-- there is no active stream).
local function dispatch_message(prepared)
    diagnostics.clear()

    local request_id = string.format("chat-%d-%d", os.time(), math.random(1000, 9999))
    M.active_stream = {
        request_id = request_id,
        rpc_request_id = nil,
    }
    M.stream_meta = {
        started_at_ns = vim.loop.hrtime and vim.loop.hrtime() or 0,
        input_tokens = 0,
        output_tokens = 0,
        estimated_cost = 0,
        cache_read = 0,
        cache_creation = 0,
        confidence_percent = nil,
        confidence_category = nil,
    }
    M.streaming_request_id = request_id
    M._start_streaming_block()

    local rpc_request_id = rpc.request("poor-cli/chatStreaming", {
        message = prepared.resolved_msg,
        contextFiles = prepared.context_files,
        requestId = request_id,
    }, function(_result, err)
        vim.schedule(function()
            if not is_active_request(request_id) then
                return
            end

            M._finalize_streaming_block(request_id)
            if err and err.code ~= -32800 then
                M.append_message("assistant", "Error: " .. require("poor-cli.rpc").format_error(err))
            end
        end)
    end)

    M.active_stream.rpc_request_id = rpc_request_id
end

-- Drain the next queued message, if any.  Called after a stream finishes or
-- is cancelled.
function M._process_queue()
    if M.active_stream then
        return -- still busy
    end
    if #M.message_queue == 0 then
        return
    end

    local next_msg = table.remove(M.message_queue, 1)

    -- update queue position indicators for remaining items
    if #M.message_queue > 0 then
        M.append_system_note(string.format("%d message(s) still queued", #M.message_queue))
    end

    dispatch_message(next_msg)
end

function M.send(message)
    if not message or message == "" then
        return
    end

    if not rpc.is_running() then
        vim.notify("[poor-cli] Server not running", vim.log.levels.WARN)
        return
    end

    M.open()

    local prepared = prepare_message(message)

    if M.active_stream then
        -- Queue the message instead of blocking with a confirm dialog.
        -- Show it in the chat immediately so the user sees it was received.
        table.insert(M.message_queue, prepared)
        M.append_message("user", message)
        M.append_system_note(string.format("Queued (position %d) — will send after current response. Press Q to manage queue.", #M.message_queue), { timeout = 8000 })
        return
    end

    M.append_message("user", message)
    dispatch_message(prepared)
end

local function format_thinking_duration(seconds)
    if seconds < 60 then
        return string.format("%d sec", seconds)
    elseif seconds < 3600 then
        return string.format("%d min", math.floor(seconds / 60))
    else
        return string.format("%d hr", math.floor(seconds / 3600))
    end
end

function M._stop_thinking_timer()
    if M._thinking_timer then
        pcall(function()
            M._thinking_timer:stop()
            M._thinking_timer:close()
        end)
        M._thinking_timer = nil
    end
end

function M._start_streaming_block()
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    local line_count = vim.api.nvim_buf_line_count(M.buf)
    vim.api.nvim_buf_set_lines(M.buf, line_count, line_count, false, { "## 🤖 Assistant", "", "💭 Thinking (0 sec)...", "" })
    M.streaming_buf_line = line_count + 2
    M._streaming_placeholder_active = true
    M._streaming_placeholder_line = line_count + 3 -- 1-indexed position of the "Thinking" line
    M.streaming_response_text = ""
    M._thinking_buffer = ""

    -- live-update the placeholder until first chunk arrives or finalize fires
    M._thinking_started_ns = (vim.loop.hrtime and vim.loop.hrtime()) or 0
    M._stop_thinking_timer()
    if vim.loop.new_timer then
        M._thinking_timer = vim.loop.new_timer()
        M._thinking_timer:start(1000, 1000, vim.schedule_wrap(function()
            if not M._streaming_placeholder_active or not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
                M._stop_thinking_timer()
                return
            end
            local elapsed = 0
            if M._thinking_started_ns > 0 and vim.loop.hrtime then
                elapsed = math.max(0, math.floor((vim.loop.hrtime() - M._thinking_started_ns) / 1000000000))
            end
            local ln = M._streaming_placeholder_line
            if ln then
                local new_text = string.format("💭 Thinking (%s)...", format_thinking_duration(elapsed))
                pcall(vim.api.nvim_buf_set_lines, M.buf, ln - 1, ln, false, { new_text })
            end
        end))
    end
end

function M._append_streaming_chunk(chunk)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    if not M.streaming_buf_line or not chunk or chunk == "" then
        return
    end

    if M._streaming_placeholder_active then
        -- first real chunk: stop timer, remove Thinking placeholder lines
        M._stop_thinking_timer()
        local ln = M.streaming_buf_line
        vim.api.nvim_buf_set_lines(M.buf, ln - 1, ln + 1, false, { "" })
        M._streaming_placeholder_active = false
    end

    M.streaming_response_text = (M.streaming_response_text or "") .. chunk
    local line_count = vim.api.nvim_buf_line_count(M.buf)
    local last_line_idx = line_count - 1
    local last_line = vim.api.nvim_buf_get_lines(M.buf, last_line_idx, line_count, false)[1] or ""

    chunk = chunk:gsub("\r\n", "\n"):gsub("\r", "\n")
    local parts = vim.split(chunk, "\n", { plain = true })
    if #parts == 1 then
        vim.api.nvim_buf_set_lines(M.buf, last_line_idx, line_count, false, { last_line .. parts[1] })
    else
        local lines = { last_line .. parts[1] }
        for index = 2, #parts do
            table.insert(lines, parts[index])
        end
        vim.api.nvim_buf_set_lines(M.buf, last_line_idx, line_count, false, lines)
    end

    if M.win and vim.api.nvim_win_is_valid(M.win) then
        local new_count = vim.api.nvim_buf_line_count(M.buf)
        pcall(vim.api.nvim_win_set_cursor, M.win, { new_count, 0 })
    end
end

local function format_stream_meta()
    local meta = M.stream_meta
    if not meta then
        return nil
    end

    -- elapsed time
    local elapsed_s = 0
    if meta.started_at_ns > 0 and vim.loop.hrtime then
        elapsed_s = math.max(0, (vim.loop.hrtime() - meta.started_at_ns) / 1e9)
    end

    local time_str
    if elapsed_s < 60 then
        time_str = string.format("%.1fs", elapsed_s)
    elseif elapsed_s < 3600 then
        time_str = string.format("%dm %ds", math.floor(elapsed_s / 60), math.floor(elapsed_s) % 60)
    else
        time_str = string.format("%dh %dm", math.floor(elapsed_s / 3600), math.floor(elapsed_s / 60) % 60)
    end

    -- tokens
    local total_tokens = meta.input_tokens + meta.output_tokens
    local tokens_str = string.format("%d tokens (%d in / %d out)", total_tokens, meta.input_tokens, meta.output_tokens)

    -- cost
    local cost_str
    if meta.estimated_cost > 0 then
        cost_str = string.format("$%.4f", meta.estimated_cost)
    else
        cost_str = "—"
    end

    -- confidence
    local conf_str = ""
    if meta.confidence_percent then
        conf_str = string.format(" | confidence: %s (%d%%)", meta.confidence_category or "?", meta.confidence_percent)
    end

    -- cache info (only if non-zero)
    local cache_str = ""
    if meta.cache_read > 0 or meta.cache_creation > 0 then
        cache_str = string.format(" | cache: %d read, %d created", meta.cache_read, meta.cache_creation)
    end

    return string.format("⏱ %s | %s | %s%s%s", time_str, tokens_str, cost_str, conf_str, cache_str)
end

function M._finalize_streaming_block(request_id)
    if request_id and not is_active_request(request_id) then
        return
    end
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    M._stop_thinking_timer()
    M._streaming_placeholder_active = false
    if M.streaming_buf_line then
        local line_count = vim.api.nvim_buf_line_count(M.buf)

        -- append response metadata footer before the separator
        local footer_lines = {}
        local meta_line = format_stream_meta()
        if meta_line then
            table.insert(footer_lines, "")
            table.insert(footer_lines, "> " .. meta_line)
        end
        table.insert(footer_lines, "")
        table.insert(footer_lines, "---")
        table.insert(footer_lines, "")

        vim.api.nvim_buf_set_lines(M.buf, line_count, line_count, false, footer_lines)
    end
    diagnostics.apply_from_text(M.streaming_response_text or "")
    M.streaming_buf_line = nil
    M.streaming_response_text = nil
    M.streaming_request_id = nil
    M.active_stream = nil
    M.stream_meta = nil

    -- drain the next queued message
    vim.schedule(function()
        M._process_queue()
    end)
end

M._thinking_buffer = ""

function M.setup_streaming_autocmds()
    local group = vim.api.nvim_create_augroup("PoorCliChatStreaming", { clear = true })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCliThinkingChunk",
        callback = function(ev)
            local data = ev.data or {}
            if not is_active_request(data.request_id or "") then
                return
            end
            if data.chunk and data.chunk ~= "" then
                vim.schedule(function()
                    M._thinking_buffer = M._thinking_buffer .. data.chunk
                    -- Update the streaming block with thinking content
                    if M.streaming_buf_line and M.buf and vim.api.nvim_buf_is_valid(M.buf) then
                        local lines = vim.split(M._thinking_buffer, "\n", { plain = true })
                        local display = { "💭 *Thinking* (" .. #lines .. " lines):" }
                        -- Show last 15 lines max
                        local start = math.max(1, #lines - 14)
                        for i = start, #lines do
                            table.insert(display, "> " .. (lines[i] or ""))
                        end
                        if start > 1 then
                            table.insert(display, 2, string.format("> ... (%d lines hidden)", start - 1))
                        end
                        vim.api.nvim_buf_set_lines(M.buf, M.streaming_buf_line - 1, -1, false, display)
                    end
                end)
            end
        end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCliStreamChunk",
        callback = function(ev)
            local data = ev.data or {}
            if not is_active_request(data.request_id or "") then
                return
            end
            if data.done then
                vim.schedule(function()
                    M._finalize_streaming_block(data.request_id)
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
            if not is_active_request(data.request_id or "") then
                return
            end
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
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCliPermissionReq",
        callback = function(ev)
            local data = ev.data or {}
            if not is_active_request(data.request_id or "") then
                return
            end
            vim.schedule(function()
                M._handle_permission_request(data)
            end)
        end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCliPlanReq",
        callback = function(ev)
            local data = ev.data or {}
            if not is_active_request(data.request_id or "") then
                return
            end
            vim.schedule(function()
                M._handle_plan_request(data.summary, data.original_request, data.steps, data.prompt_id)
            end)
        end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCliProgress",
        callback = function(ev)
            local data = ev.data or {}
            if not is_active_request(data.request_id or "") then
                return
            end
            vim.schedule(function()
                if data.message and data.message ~= "" then
                    emit_debug_note({ "_" .. tostring(data.message) .. "_", "" })
                end
            end)
        end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCliCostUpdate",
        callback = function(ev)
            local data = ev.data or {}
            if not is_active_request(data.request_id or "") then
                return
            end
            vim.schedule(function()
                -- accumulate into stream_meta (server may send multiple updates)
                if M.stream_meta then
                    M.stream_meta.input_tokens = M.stream_meta.input_tokens + (data.input_tokens or 0)
                    M.stream_meta.output_tokens = M.stream_meta.output_tokens + (data.output_tokens or 0)
                    M.stream_meta.estimated_cost = M.stream_meta.estimated_cost + (data.estimated_cost or 0)
                    M.stream_meta.cache_read = M.stream_meta.cache_read + (data.cache_read_input_tokens or 0)
                    M.stream_meta.cache_creation = M.stream_meta.cache_creation + (data.cache_creation_input_tokens or 0)
                    if data.confidence_percent then
                        M.stream_meta.confidence_percent = data.confidence_percent
                        M.stream_meta.confidence_category = data.confidence_category
                    end
                end

                local cache_bits = ""
                if (data.cache_read_input_tokens or 0) > 0 or (data.cache_creation_input_tokens or 0) > 0 then
                    cache_bits = string.format(
                        " cache[r=%s c=%s]",
                        tostring(data.cache_read_input_tokens or 0),
                        tostring(data.cache_creation_input_tokens or 0)
                    )
                end
                emit_debug_note({
                    string.format(
                        "_tokens in=%s out=%s cost=%s%s_",
                        tostring(data.input_tokens or 0),
                        tostring(data.output_tokens or 0),
                        tostring(data.estimated_cost or 0),
                        cache_bits
                    ),
                    "",
                })
            end)
        end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCliRoomEvent",
        callback = function(ev)
            local data = ev.data or {}
            vim.schedule(function()
                M._handle_room_event(data)
            end)
        end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCliMemberRoleUpdated",
        callback = function(ev)
            local data = ev.data or {}
            vim.schedule(function()
                M._handle_member_role_update(data)
            end)
        end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCliSuggestion",
        callback = function(ev)
            local data = ev.data or {}
            vim.schedule(function()
                M._handle_suggestion(data)
            end)
        end,
    })
end

M._perm_ui = { buf = nil, win = nil }

local function perm_ui_close()
    local ui = M._perm_ui
    if ui.win and vim.api.nvim_win_is_valid(ui.win) then
        vim.api.nvim_win_close(ui.win, true)
    end
    ui.win = nil
    if ui.buf and vim.api.nvim_buf_is_valid(ui.buf) then
        vim.api.nvim_buf_delete(ui.buf, { force = true })
    end
    ui.buf = nil
end

function M._handle_permission_request(data)
    local tool_name = data.tool_name or "tool"
    local tool_args = data.tool_args or {}
    local prompt_id = data.prompt_id or ""
    local operation = data.operation or tool_name
    local paths = data.paths or {}
    local diff = data.diff or ""
    local message = data.message or ""
    local capabilities = data.capabilities or {}
    local sandbox_preset = data.sandbox_preset or ""

    perm_ui_close()

    -- build content lines
    local lines = {
        "# Permission Request",
        "",
        string.format("**%s** wants to execute: **%s**", tool_name, operation),
        "",
    }

    -- message from server
    if message ~= "" then
        table.insert(lines, message)
        table.insert(lines, "")
    end

    -- affected paths
    if #paths > 0 then
        table.insert(lines, "## Paths")
        table.insert(lines, "")
        for _, p in ipairs(paths) do
            table.insert(lines, "  " .. tostring(p))
        end
        table.insert(lines, "")
    end

    -- capabilities
    if #capabilities > 0 then
        table.insert(lines, "## Capabilities")
        table.insert(lines, "")
        for _, cap in ipairs(capabilities) do
            table.insert(lines, "  • " .. tostring(cap))
        end
        table.insert(lines, "")
    end

    -- sandbox preset
    if sandbox_preset ~= "" then
        table.insert(lines, string.format("Sandbox: **%s**", sandbox_preset))
        table.insert(lines, "")
    end

    -- arguments
    local args_str = type(tool_args) == "table" and vim.inspect(tool_args) or tostring(tool_args)
    if args_str ~= "" and args_str ~= "{}" then
        table.insert(lines, "## Arguments")
        table.insert(lines, "")
        table.insert(lines, "```")
        for _, line in ipairs(vim.split(args_str, "\n", { plain = true })) do
            table.insert(lines, line)
        end
        table.insert(lines, "```")
        table.insert(lines, "")
    end

    -- diff preview
    if diff ~= "" then
        table.insert(lines, "## Diff")
        table.insert(lines, "")
        table.insert(lines, "```diff")
        for _, line in ipairs(vim.split(diff, "\n", { plain = true })) do
            table.insert(lines, line)
        end
        table.insert(lines, "```")
        table.insert(lines, "")
    end

    -- footer
    table.insert(lines, "---")
    table.insert(lines, "a = approve | d = deny | q = deny & close")

    -- create floating window
    local ui = M._perm_ui
    ui.buf = vim.api.nvim_create_buf(false, true)
    vim.bo[ui.buf].buftype = "nofile"
    vim.bo[ui.buf].bufhidden = "wipe"
    vim.bo[ui.buf].swapfile = false
    vim.bo[ui.buf].filetype = "markdown"
    vim.api.nvim_buf_set_name(ui.buf, "[poor-cli permission]")

    vim.bo[ui.buf].modifiable = true
    vim.api.nvim_buf_set_lines(ui.buf, 0, -1, false, lines)
    vim.bo[ui.buf].modifiable = false

    local width = math.min(90, math.floor(vim.o.columns * 0.7))
    local height = math.min(#lines + 2, math.floor(vim.o.lines * 0.7))
    ui.win = vim.api.nvim_open_win(ui.buf, true, {
        relative = "editor",
        width = width,
        height = height,
        col = math.floor((vim.o.columns - width) / 2),
        row = math.floor((vim.o.lines - height) / 2),
        style = "minimal",
        border = "rounded",
        title = " Approve Tool Call? ",
        title_pos = "center",
    })

    local function respond(allowed)
        rpc.notify("poor-cli/permissionRes", {
            promptId = prompt_id,
            allowed = allowed,
        })
        perm_ui_close()
    end

    local buf = ui.buf
    vim.keymap.set("n", "a", function() respond(true) end, { buffer = buf, nowait = true })
    vim.keymap.set("n", "y", function() respond(true) end, { buffer = buf, nowait = true })
    vim.keymap.set("n", "<CR>", function() respond(true) end, { buffer = buf, nowait = true })
    vim.keymap.set("n", "d", function() respond(false) end, { buffer = buf, nowait = true })
    vim.keymap.set("n", "n", function() respond(false) end, { buffer = buf, nowait = true })
    vim.keymap.set("n", "q", function() respond(false) end, { buffer = buf, nowait = true })
    vim.keymap.set("n", "<Esc>", function() respond(false) end, { buffer = buf, nowait = true })
end

function M._handle_plan_request(summary, original_request, steps, prompt_id)
    local plan = require("poor-cli.plan")
    plan.open({
        summary = summary or "",
        original_request = original_request or "",
        steps = steps or {},
        prompt_id = prompt_id or "",
    })
    if summary and summary ~= "" then
        M.open()
        M.append_system_note("Plan review requested — see floating window (a=approve, r=reject)")
    end
end

function M._handle_room_event(data)
    local event_type = data.event_type or ""
    if event_type == "" then
        return
    end

    local notable_events = {
        member_joined = true,
        member_pending = true,
        member_approved = true,
        member_denied = true,
        member_removed = true,
        member_kicked = true,
        member_left = true,
        role_handoff = true,
        lobby_updated = true,
        preset_updated = true,
        agenda_added = true,
        agenda_resolved = true,
        hand_raised = true,
        hand_lowered = true,
        next_driver_selected = true,
        token_rotated = true,
        token_revoked = true,
    }
    if not notable_events[event_type] then
        return
    end

    local room = data.room or ""
    local summary = string.format(
        "Room `%s`: %s (%d members, queue %d)",
        room,
        event_type:gsub("_", " "),
        tonumber(data.member_count) or 0,
        tonumber(data.queue_depth) or 0
    )
    vim.notify("[poor-cli] " .. summary, vim.log.levels.INFO)
    if M.buf and vim.api.nvim_buf_is_valid(M.buf) then
        M.append_system_note(summary)
    end
end

function M._handle_member_role_update(data)
    local connection_id = data.connection_id or ""
    local role = data.role or ""
    if connection_id == "" or role == "" then
        return
    end

    local summary = string.format("Role update: %s -> %s", connection_id, role)
    vim.notify("[poor-cli] " .. summary, vim.log.levels.INFO)
    if M.buf and vim.api.nvim_buf_is_valid(M.buf) then
        M.append_system_note(summary)
    end
end

function M._handle_suggestion(data)
    local sender = data.sender or "teammate"
    local text = data.text or ""
    if text == "" then
        return
    end

    local summary = string.format("Suggestion from %s: %s", sender, text)
    vim.notify("[poor-cli] " .. summary, vim.log.levels.INFO)
    M.open()
    M.append_system_note(summary)
end

function M._append_tool_call(name, args)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    local line_count = vim.api.nvim_buf_line_count(M.buf)
    local args_str = type(args) == "table" and vim.inspect(args) or tostring(args or "")
    vim.api.nvim_buf_set_lines(M.buf, line_count, line_count, false, {
        "**🔧 " .. (name or "tool") .. "**",
        "```",
        args_str,
        "```",
        "",
    })
end

function M._append_tool_result(name, result)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    local line_count = vim.api.nvim_buf_line_count(M.buf)
    local result_str = tostring(result or "")
    if #result_str > 500 then
        result_str = result_str:sub(1, 500) .. "…"
    end
    vim.api.nvim_buf_set_lines(M.buf, line_count, line_count, false, {
        "**✓ " .. (name or "tool") .. " result**",
        "```",
        result_str,
        "```",
        "",
    })
end

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

function M.get_context_files()
    local files = {}
    local seen = {}
    local max_context_files = tonumber(config.get("max_context_files")) or 20
    local should_cap = max_context_files > 0

    for _, bufnr in ipairs(vim.api.nvim_list_bufs()) do
        if vim.api.nvim_buf_is_loaded(bufnr) then
            local name = vim.api.nvim_buf_get_name(bufnr)
            if name ~= "" and vim.fn.filereadable(name) == 1 then
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

function M.setup_buffer_keymaps()
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end

    vim.keymap.set("n", "q", function()
        if M.active_stream then
            M.cancel_active_stream("Cancelled by user.")
        else
            M.close()
        end
    end, { buffer = M.buf, desc = "Cancel stream or close chat", nowait = true })

    vim.keymap.set("n", "<Esc>", function()
        if M.active_stream then
            M.cancel_active_stream("Cancelled by user.")
        end
    end, { buffer = M.buf, desc = "Cancel active stream", nowait = true })

    vim.keymap.set("n", "<C-c>", function()
        if M.active_stream then
            M.cancel_active_stream("Cancelled by user.")
        end
    end, { buffer = M.buf, desc = "Cancel active stream", nowait = true })

    vim.keymap.set("n", "Q", function()
        M.open_queue_manager()
    end, { buffer = M.buf, desc = "Open queue manager", nowait = true })

    vim.keymap.set("n", "<CR>", function()
        M.prompt_and_send()
    end, { buffer = M.buf, desc = "Send message", nowait = true, silent = true })

    -- re-apply on BufEnter in case a filetype plugin (e.g. vim-markdown) clobbers <CR>
    vim.api.nvim_create_autocmd("BufEnter", {
        buffer = M.buf,
        callback = function()
            vim.keymap.set("n", "<CR>", function()
                M.prompt_and_send()
            end, { buffer = M.buf, desc = "Send message", nowait = true, silent = true })
        end,
    })
end

-- ─────────────────── Chat Input with @/slash completion ───────────────────

-- slash commands available in chat input
local SLASH_COMMANDS = {
    { name = "/clear",       desc = "Clear chat history" },
    { name = "/cancel",      desc = "Cancel active request" },
    { name = "/queue",       desc = "Open queue manager" },
    { name = "/resume",      desc = "Restore last saved session" },
    { name = "/sessions",    desc = "List saved sessions" },
    { name = "/save",        desc = "Save current session" },
    { name = "/status",      desc = "Show session status" },
    { name = "/switch",      desc = "Switch provider/model" },
    { name = "/explain",     desc = "Explain selected code" },
    { name = "/refactor",    desc = "Refactor selected code" },
    { name = "/test",        desc = "Generate tests" },
    { name = "/doc",         desc = "Generate documentation" },
    { name = "/fix",         desc = "Fix diagnostics" },
    { name = "/context",     desc = "Show context info" },
    { name = "/cost",        desc = "Show token usage and cost" },
    { name = "/doctor",      desc = "Run diagnostics" },
    { name = "/help",        desc = "List all commands" },
}

-- map slash commands to their PoorCli handlers
local SLASH_HANDLERS = {
    ["/clear"]    = function() M.clear() end,
    ["/cancel"]   = function() M.cancel_active_stream("Cancelled by user.") end,
    ["/queue"]    = function() M.open_queue_manager() end,
    ["/resume"]   = function() vim.cmd("PoorCliSessionRestore") end,
    ["/sessions"] = function() vim.cmd("PoorCliSessions") end,
    ["/save"]     = function() vim.cmd("PoorCliSessionSave") end,
    ["/status"]   = function() vim.cmd("PoorCliStatus") end,
    ["/switch"]   = function() vim.cmd("PoorCliSwitchProvider") end,
    ["/explain"]  = function() vim.cmd("PoorCliExplain") end,
    ["/refactor"] = function() vim.cmd("PoorCliRefactor") end,
    ["/test"]     = function() vim.cmd("PoorCliTest") end,
    ["/doc"]      = function() vim.cmd("PoorCliDoc") end,
    ["/fix"]      = function() vim.cmd("PoorCliFixDiagnostics") end,
    ["/context"]  = function() vim.cmd("PoorCliContext") end,
    ["/cost"]     = function() vim.cmd("PoorCliCost") end,
    ["/doctor"]   = function() vim.cmd("PoorCliDoctor") end,
    ["/help"]     = function() vim.cmd("PoorCliHelp") end,
}

M._input_popup = { buf = nil, win = nil, menu_buf = nil, menu_win = nil }

local function input_close_menu()
    local ip = M._input_popup
    if ip.menu_win and vim.api.nvim_win_is_valid(ip.menu_win) then
        vim.api.nvim_win_close(ip.menu_win, true)
    end
    ip.menu_win = nil
    if ip.menu_buf and vim.api.nvim_buf_is_valid(ip.menu_buf) then
        vim.api.nvim_buf_delete(ip.menu_buf, { force = true })
    end
    ip.menu_buf = nil
end

local function input_close()
    input_close_menu()
    local ip = M._input_popup
    if ip.win and vim.api.nvim_win_is_valid(ip.win) then
        vim.api.nvim_win_close(ip.win, true)
    end
    ip.win = nil
    if ip.buf and vim.api.nvim_buf_is_valid(ip.buf) then
        vim.api.nvim_buf_delete(ip.buf, { force = true })
    end
    ip.buf = nil
end

local function get_file_completions(prefix)
    local items = {}
    local seen = {}
    -- open buffers first
    for _, bufnr in ipairs(vim.api.nvim_list_bufs()) do
        if vim.api.nvim_buf_is_loaded(bufnr) then
            local name = vim.api.nvim_buf_get_name(bufnr)
            if name ~= "" and vim.fn.filereadable(name) == 1 then
                local rel = vim.fn.fnamemodify(name, ":~:.")
                if not seen[rel] and (prefix == "" or rel:find(prefix, 1, true)) then
                    seen[rel] = true
                    table.insert(items, { text = "@file:" .. rel, desc = "(buffer)" })
                end
            end
        end
    end
    -- project files from cwd (scan shallow, cap at 30)
    local cwd = vim.fn.getcwd()
    local project_files = scan_workspace_files(cwd, 0, {})
    for _, abs_path in ipairs(project_files) do
        local rel = vim.fn.fnamemodify(abs_path, ":~:.")
        if not seen[rel] and (prefix == "" or rel:find(prefix, 1, true)) then
            seen[rel] = true
            table.insert(items, { text = "@file:" .. rel, desc = "(project)" })
        end
        if #items >= 30 then break end
    end
    -- @workspace
    if prefix == "" or ("workspace"):find(prefix, 1, true) then
        table.insert(items, { text = "@workspace", desc = "(include project tree)" })
    end
    return items
end

local function get_slash_completions(prefix)
    local items = {}
    for _, cmd in ipairs(SLASH_COMMANDS) do
        if prefix == "" or cmd.name:find(prefix, 1, true) then
            table.insert(items, { text = cmd.name, desc = cmd.desc })
        end
    end
    return items
end

local function show_completion_menu(items)
    input_close_menu()
    if #items == 0 then return end

    local ip = M._input_popup
    if not ip.win or not vim.api.nvim_win_is_valid(ip.win) then return end

    local display_lines = {}
    for _, item in ipairs(items) do
        table.insert(display_lines, string.format(" %s  %s", item.text, item.desc or ""))
    end

    ip.menu_buf = vim.api.nvim_create_buf(false, true)
    vim.bo[ip.menu_buf].buftype = "nofile"
    vim.bo[ip.menu_buf].bufhidden = "wipe"
    vim.api.nvim_buf_set_lines(ip.menu_buf, 0, -1, false, display_lines)

    local input_pos = vim.api.nvim_win_get_position(ip.win)
    local menu_width = math.min(60, math.max(30, vim.api.nvim_win_get_width(ip.win)))
    local menu_height = math.min(#items, 10)

    ip.menu_win = vim.api.nvim_open_win(ip.menu_buf, false, {
        relative = "editor",
        width = menu_width,
        height = menu_height,
        row = input_pos[1] - menu_height - 1,
        col = input_pos[2],
        style = "minimal",
        border = "single",
        focusable = false,
        zindex = 60,
    })

    ip._menu_items = items
    ip._menu_sel = 0
end

local function update_completions()
    local ip = M._input_popup
    if not ip.buf or not vim.api.nvim_buf_is_valid(ip.buf) then return end

    local line = vim.api.nvim_buf_get_lines(ip.buf, 0, 1, false)[1] or ""
    local col = vim.api.nvim_win_get_cursor(ip.win)[2]
    local before = line:sub(1, col)

    -- check for / (must be at start of line)
    local slash_match = before:match("^(/[%w]*)$")
    if slash_match then
        show_completion_menu(get_slash_completions(slash_match))
        return
    end

    -- check for @ (requires literal @ character)
    local at_pos = before:find("@[%w%._/%-~]*$")
    if at_pos then
        local at_match = before:sub(at_pos + 1) -- text after the @
        show_completion_menu(get_file_completions(at_match))
        return
    end

    input_close_menu()
end

local function accept_completion()
    local ip = M._input_popup
    if not ip._menu_items or #ip._menu_items == 0 then return false end
    if not ip.buf or not vim.api.nvim_buf_is_valid(ip.buf) then return false end

    local sel = ip._menu_sel
    if sel < 1 or sel > #ip._menu_items then sel = 1 end
    local item = ip._menu_items[sel]
    if not item then return false end

    local line = vim.api.nvim_buf_get_lines(ip.buf, 0, 1, false)[1] or ""
    local col = vim.api.nvim_win_get_cursor(ip.win)[2]
    local before = line:sub(1, col)
    local after = line:sub(col + 1)

    -- replace the trigger prefix with the completion text
    local new_before
    if before:match("@[%w%._/%-~]*$") then
        new_before = before:gsub("@[%w%._/%-~]*$", item.text)
    elseif before:match("^/[%w]*$") then
        new_before = item.text
    else
        return false
    end

    local new_line = new_before .. " " .. after
    vim.api.nvim_buf_set_lines(ip.buf, 0, 1, false, { new_line })
    pcall(vim.api.nvim_win_set_cursor, ip.win, { 1, #new_before + 1 })
    input_close_menu()
    return true
end

local function menu_select_next()
    local ip = M._input_popup
    if not ip._menu_items or #ip._menu_items == 0 then return end
    ip._menu_sel = ((ip._menu_sel or 0) % #ip._menu_items) + 1
    if ip.menu_win and vim.api.nvim_win_is_valid(ip.menu_win) then
        pcall(vim.api.nvim_win_set_cursor, ip.menu_win, { ip._menu_sel, 0 })
    end
end

local function menu_select_prev()
    local ip = M._input_popup
    if not ip._menu_items or #ip._menu_items == 0 then return end
    ip._menu_sel = ((ip._menu_sel or 2) - 2) % #ip._menu_items + 1
    if ip.menu_win and vim.api.nvim_win_is_valid(ip.menu_win) then
        pcall(vim.api.nvim_win_set_cursor, ip.menu_win, { ip._menu_sel, 0 })
    end
end

function M.prompt_and_send()
    M.open()

    input_close() -- close any existing

    local ip = M._input_popup
    ip.buf = vim.api.nvim_create_buf(false, true)
    vim.bo[ip.buf].buftype = "nofile"
    vim.bo[ip.buf].bufhidden = "wipe"
    vim.bo[ip.buf].swapfile = false
    vim.bo[ip.buf].completefunc = ""
    vim.bo[ip.buf].omnifunc = ""
    vim.bo[ip.buf].complete = ""

    -- position at bottom of chat window
    local chat_width = M.win and vim.api.nvim_win_is_valid(M.win) and vim.api.nvim_win_get_width(M.win) or 60
    local chat_pos = M.win and vim.api.nvim_win_is_valid(M.win) and vim.api.nvim_win_get_position(M.win) or { 0, 0 }
    local chat_height = M.win and vim.api.nvim_win_is_valid(M.win) and vim.api.nvim_win_get_height(M.win) or 20

    local input_width = math.max(20, chat_width - 2)
    ip.win = vim.api.nvim_open_win(ip.buf, true, {
        relative = "editor",
        width = input_width,
        height = 1,
        row = chat_pos[1] + chat_height - 1,
        col = chat_pos[2] + 1,
        style = "minimal",
        border = "single",
        title = " Message (@file /cmd) ",
        title_pos = "center",
        zindex = 55,
    })

    -- detach nvim-cmp if present to prevent it from hijacking completions
    local cmp_ok, cmp = pcall(require, "cmp")
    if cmp_ok and cmp.setup and cmp.setup.buffer then
        pcall(cmp.setup.buffer, { enabled = false })
    end

    vim.cmd("startinsert")

    local buf = ip.buf

    -- submit
    vim.keymap.set("i", "<CR>", function()
        local line = vim.api.nvim_buf_get_lines(buf, 0, 1, false)[1] or ""
        input_close()
        vim.cmd("stopinsert")
        if line == "" then return end

        -- check for slash command
        local cmd = line:match("^(/[%w]+)")
        if cmd and SLASH_HANDLERS[cmd] then
            SLASH_HANDLERS[cmd]()
            return
        end

        M.send(line)
    end, { buffer = buf, nowait = true })

    -- cancel
    vim.keymap.set("i", "<Esc>", function()
        input_close()
        vim.cmd("stopinsert")
    end, { buffer = buf, nowait = true })

    vim.keymap.set("n", "<Esc>", function()
        input_close()
    end, { buffer = buf, nowait = true })

    vim.keymap.set("n", "q", function()
        input_close()
    end, { buffer = buf, nowait = true })

    -- Tab to accept completion, Shift-Tab or Ctrl-p to navigate
    vim.keymap.set("i", "<Tab>", function()
        if not accept_completion() then
            vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes("<Tab>", true, false, true), "n", false)
        end
    end, { buffer = buf, nowait = true })

    vim.keymap.set("i", "<C-n>", function() menu_select_next() end, { buffer = buf, nowait = true })
    vim.keymap.set("i", "<C-p>", function() menu_select_prev() end, { buffer = buf, nowait = true })

    -- live update completions on text change
    vim.api.nvim_create_autocmd({ "TextChangedI", "TextChanged" }, {
        buffer = buf,
        callback = function()
            vim.schedule(update_completions)
        end,
    })
end

function M.append_loading()
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end

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

function M.remove_loading()
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) or not M.loading_marker then
        return
    end

    local marker = vim.api.nvim_buf_get_extmark_by_id(M.buf, M.loading_ns, M.loading_marker, {
        details = true,
    })
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

function M.send_with_selection()
    -- use marks instead of mode check (mode may have exited by keymap fire time)
    local start_line = vim.fn.line("'<")
    local end_line = vim.fn.line("'>")
    if start_line == 0 or end_line == 0 or start_line > end_line then
        vim.notify("[poor-cli] Select text first", vim.log.levels.WARN)
        return
    end
    local lines = vim.api.nvim_buf_get_lines(0, start_line - 1, end_line, false)
    local selected_text = table.concat(lines, "\n")
    if not selected_text or selected_text == "" then
        return
    end

    M.open()
    vim.ui.input({ prompt = "Ask about selection: " }, function(question)
        if not question or question == "" then
            question = "Please explain this code."
        end

        local message = question .. "\n\n```\n" .. selected_text .. "\n```"
        M.send(message)
    end)
end

function M.clear()
    if M.buf and vim.api.nvim_buf_is_valid(M.buf) then
        vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, {
            "# poor-cli Chat",
            "",
            "Use `:PoorCliSend` or press `<CR>` at the bottom to send a message.",
            "",
            "---",
            "",
        })
    end
    M.history = {}
    M.active_stream = nil
    M.streaming_buf_line = nil
    M.streaming_request_id = nil
    M.streaming_response_text = nil
    M.stream_meta = nil
    M.message_queue = {}
    diagnostics.clear()

    if rpc.is_running() then
        rpc.request("poor-cli/clearHistory", {}, function() end)
    end
end

function M.get_last_user_message()
    for i = #M.history, 1, -1 do
        if M.history[i].role == "user" then
            return M.history[i].content
        end
    end
    return nil
end

-- ─────────────────────── Queue Manager UI ───────────────────────

M._queue_mgr = { buf = nil, win = nil }

local function queue_mgr_close()
    local mgr = M._queue_mgr
    if mgr.win and vim.api.nvim_win_is_valid(mgr.win) then
        vim.api.nvim_win_close(mgr.win, true)
    end
    mgr.win = nil
    if mgr.buf and vim.api.nvim_buf_is_valid(mgr.buf) then
        vim.api.nvim_buf_delete(mgr.buf, { force = true })
    end
    mgr.buf = nil
end

-- returns 1-based queue index from cursor position, or nil
local function queue_mgr_cursor_index()
    local mgr = M._queue_mgr
    if not mgr.win or not vim.api.nvim_win_is_valid(mgr.win) then return nil end
    local row = vim.api.nvim_win_get_cursor(mgr.win)[1] -- 1-based
    -- header is 4 lines, then each entry is 3 lines (number line, preview, blank)
    if row <= 4 then return nil end
    local idx = math.floor((row - 5) / 3) + 1
    if idx < 1 or idx > #M.message_queue then return nil end
    return idx
end

local function queue_mgr_render()
    local mgr = M._queue_mgr
    if not mgr.buf or not vim.api.nvim_buf_is_valid(mgr.buf) then return end

    local lines = {
        "# Message Queue",
        "",
        string.format("%d queued message(s).  e=edit  d=delete  K=up  J=down  q=close", #M.message_queue),
        "",
    }

    if #M.message_queue == 0 then
        table.insert(lines, "_Queue is empty._")
    else
        for i, item in ipairs(M.message_queue) do
            local preview = item.message:gsub("\n", " ")
            if #preview > 70 then
                preview = preview:sub(1, 67) .. "..."
            end
            table.insert(lines, string.format("  %d. %s", i, preview))
            table.insert(lines, string.format("     (%d chars)", #item.message))
            table.insert(lines, "")
        end
    end

    vim.bo[mgr.buf].modifiable = true
    vim.api.nvim_buf_set_lines(mgr.buf, 0, -1, false, lines)
    vim.bo[mgr.buf].modifiable = false
end

function M.open_queue_manager()
    if #M.message_queue == 0 then
        vim.notify("[poor-cli] Queue is empty", vim.log.levels.INFO)
        return
    end

    queue_mgr_close() -- close any existing

    local mgr = M._queue_mgr
    mgr.buf = vim.api.nvim_create_buf(false, true)
    vim.bo[mgr.buf].buftype = "nofile"
    vim.bo[mgr.buf].bufhidden = "wipe"
    vim.bo[mgr.buf].swapfile = false
    vim.bo[mgr.buf].filetype = "markdown"
    vim.api.nvim_buf_set_name(mgr.buf, "[poor-cli queue]")

    local width = math.min(80, math.floor(vim.o.columns * 0.6))
    local height = math.min(20, math.max(8, #M.message_queue * 3 + 5))
    mgr.win = vim.api.nvim_open_win(mgr.buf, true, {
        relative = "editor",
        width = width,
        height = height,
        col = math.floor((vim.o.columns - width) / 2),
        row = math.floor((vim.o.lines - height) / 2),
        style = "minimal",
        border = "rounded",
        title = " Message Queue ",
        title_pos = "center",
    })

    queue_mgr_render()

    -- position cursor on first entry
    if #M.message_queue > 0 then
        pcall(vim.api.nvim_win_set_cursor, mgr.win, { 5, 0 })
    end

    -- keymaps
    local buf = mgr.buf

    -- close
    vim.keymap.set("n", "q", queue_mgr_close, { buffer = buf, nowait = true })
    vim.keymap.set("n", "<Esc>", queue_mgr_close, { buffer = buf, nowait = true })

    -- delete
    vim.keymap.set("n", "d", function()
        local idx = queue_mgr_cursor_index()
        if not idx then return end
        table.remove(M.message_queue, idx)
        queue_mgr_render()
        if #M.message_queue == 0 then
            queue_mgr_close()
            vim.notify("[poor-cli] Queue cleared", vim.log.levels.INFO)
        end
    end, { buffer = buf, nowait = true })

    vim.keymap.set("n", "x", function()
        local idx = queue_mgr_cursor_index()
        if not idx then return end
        table.remove(M.message_queue, idx)
        queue_mgr_render()
        if #M.message_queue == 0 then
            queue_mgr_close()
            vim.notify("[poor-cli] Queue cleared", vim.log.levels.INFO)
        end
    end, { buffer = buf, nowait = true })

    -- edit
    vim.keymap.set("n", "e", function()
        local idx = queue_mgr_cursor_index()
        if not idx then return end
        local item = M.message_queue[idx]
        vim.ui.input({ prompt = "Edit message: ", default = item.message }, function(new_msg)
            if not new_msg or new_msg == "" then return end
            -- re-prepare with new message text
            local resolved_msg, mention_files = M._resolve_mentions(new_msg)
            local error_keywords = { "error", "warning", "issue", "bug", "fix", "broken", "fail", "diagnostic" }
            local lower_msg = new_msg:lower()
            for _, kw in ipairs(error_keywords) do
                if lower_msg:find(kw, 1, true) then
                    local diag_ctx = diagnostics.get_workspace_diagnostics_summary()
                    if diag_ctx then
                        resolved_msg = resolved_msg .. "\n\n" .. diag_ctx
                    end
                    break
                end
            end
            local context_files = M.get_context_files()
            for _, file_path in ipairs(mention_files) do
                table.insert(context_files, file_path)
            end
            M.message_queue[idx] = {
                message = new_msg,
                resolved_msg = resolved_msg,
                context_files = context_files,
            }
            vim.schedule(queue_mgr_render)
        end)
    end, { buffer = buf, nowait = true })

    -- move up
    vim.keymap.set("n", "K", function()
        local idx = queue_mgr_cursor_index()
        if not idx or idx <= 1 then return end
        M.message_queue[idx], M.message_queue[idx - 1] = M.message_queue[idx - 1], M.message_queue[idx]
        queue_mgr_render()
        -- move cursor to follow the item
        pcall(vim.api.nvim_win_set_cursor, mgr.win, { 5 + (idx - 2) * 3, 0 })
    end, { buffer = buf, nowait = true })

    -- move down
    vim.keymap.set("n", "J", function()
        local idx = queue_mgr_cursor_index()
        if not idx or idx >= #M.message_queue then return end
        M.message_queue[idx], M.message_queue[idx + 1] = M.message_queue[idx + 1], M.message_queue[idx]
        queue_mgr_render()
        -- move cursor to follow the item
        pcall(vim.api.nvim_win_set_cursor, mgr.win, { 5 + idx * 3, 0 })
    end, { buffer = buf, nowait = true })

    -- clear all
    vim.keymap.set("n", "D", function()
        M.message_queue = {}
        queue_mgr_close()
        vim.notify("[poor-cli] Queue cleared", vim.log.levels.INFO)
    end, { buffer = buf, nowait = true })
end

return M
