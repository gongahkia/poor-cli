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

local function is_active_request(request_id)
    return M.active_stream and M.active_stream.request_id ~= "" and M.active_stream.request_id == request_id
end

local function emit_debug_note(lines)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
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

function M.append_system_note(content)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end

    local lines = { "## ℹ️ System", "" }
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
    M.active_stream = nil
    M.streaming_request_id = nil
    M.streaming_response_text = nil
    M.streaming_buf_line = nil
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
    return true
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
    if M.active_stream then
        M.cancel_active_stream("Cancelled previous chat request.")
    end

    local resolved_msg, mention_files = M._resolve_mentions(message)
    diagnostics.clear()

    -- auto-inject LSP diagnostics when user asks about errors/warnings/issues
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

    M.append_message("user", message)

    local context_files = M.get_context_files()
    for _, file_path in ipairs(mention_files) do
        table.insert(context_files, file_path)
    end

    local request_id = string.format("chat-%d-%d", os.time(), math.random(1000, 9999))
    M.active_stream = {
        request_id = request_id,
        rpc_request_id = nil,
    }
    M.streaming_request_id = request_id
    M._start_streaming_block()

    local rpc_request_id = rpc.request("poor-cli/chatStreaming", {
        message = resolved_msg,
        contextFiles = context_files,
        requestId = request_id,
    }, function(_result, err)
        vim.schedule(function()
            if not is_active_request(request_id) then
                return
            end

            M._finalize_streaming_block(request_id)
            if err and err.code ~= -32800 then
                M.append_message("assistant", "Error: " .. vim.inspect(err))
            end
        end)
    end)

    M.active_stream.rpc_request_id = rpc_request_id
end

function M._start_streaming_block()
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    local line_count = vim.api.nvim_buf_line_count(M.buf)
    vim.api.nvim_buf_set_lines(M.buf, line_count, line_count, false, { "## 🤖 Assistant", "" })
    M.streaming_buf_line = line_count + 2
    M.streaming_response_text = ""
    M._thinking_buffer = ""
end

function M._append_streaming_chunk(chunk)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    if not M.streaming_buf_line or not chunk or chunk == "" then
        return
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

function M._finalize_streaming_block(request_id)
    if request_id and not is_active_request(request_id) then
        return
    end
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    if M.streaming_buf_line then
        local line_count = vim.api.nvim_buf_line_count(M.buf)
        vim.api.nvim_buf_set_lines(M.buf, line_count, line_count, false, { "", "---", "" })
    end
    diagnostics.apply_from_text(M.streaming_response_text or "")
    M.streaming_buf_line = nil
    M.streaming_response_text = nil
    M.streaming_request_id = nil
    M.active_stream = nil
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
                M._handle_permission_request(data.tool_name, data.tool_args, data.prompt_id)
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

function M._handle_permission_request(tool_name, tool_args, prompt_id)
    local args_str = type(tool_args) == "table" and vim.inspect(tool_args) or tostring(tool_args or "")
    local msg = string.format("Allow %s?\n%s", tool_name or "tool", args_str)
    vim.ui.select({ "Allow", "Deny" }, { prompt = msg }, function(choice)
        local allowed = choice == "Allow"
        rpc.notify("poor-cli/permissionRes", {
            promptId = prompt_id or "",
            allowed = allowed,
        })
    end)
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
        M.close()
    end, { buffer = M.buf, desc = "Close chat" })

    vim.keymap.set("n", "<CR>", function()
        M.prompt_and_send()
    end, { buffer = M.buf, desc = "Send message" })
end

function M.prompt_and_send()
    M.open()
    vim.ui.input({ prompt = "Message: " }, function(input)
        if input and input ~= "" then
            M.send(input)
        end
    end)
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

return M
