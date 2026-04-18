local rpc = require("poor-cli.rpc")

local M = {}

M.streams = {}
M.events = {}
M.by_id = {}
M.expanded = {}
M.buf = nil
M.win = nil
M.line_events = {}
M.widths = { status = 10, duration = 8, tool = 18, args = 52 }
M._setup_done = false

local glyphs = {
    pending = "*",
    running = "*",
    done = "ok",
    failed = "!!",
    cancelled = "xx",
    denied = "!!",
}

local function state_for(event_id)
    local key = tostring(event_id or "")
    M.streams[key] = M.streams[key] or { next_index = 0, pending = {}, chunks_processed = 0 }
    return M.streams[key]
end

local function ack(event_id, chunks_processed)
    if event_id == nil or event_id == "" then
        return
    end
    rpc.notify("poor-cli/toolStreamAck", {
        eventId = event_id,
        chunksProcessed = chunks_processed,
    })
end

local function truncate(text, width)
    text = tostring(text or ""):gsub("\n.*", "")
    if #text <= width then
        return text
    end
    return text:sub(1, math.max(1, width - 3)) .. "..."
end

local function pad(text, width)
    text = truncate(text, width)
    return text .. string.rep(" ", math.max(0, width - #text))
end

local function event_id(event)
    return tostring(event.eventId or event.event_id or "")
end

local function turn_id(event)
    return tostring(event.turnId or event.turn_id or "")
end

local function normalize(event)
    event.eventId = event.eventId or event.event_id
    event.turnId = event.turnId or event.turn_id
    event.toolCallId = event.toolCallId or event.tool_call_id
    event.toolName = event.toolName or event.tool_name or "tool"
    event.argsPreview = event.argsPreview or event.args_preview or ""
    event.argsFull = event.argsFull or event.args_full or {}
    event.resultPreview = event.resultPreview or event.result_preview or ""
    event.resultFull = event.resultFull or event.result_full or ""
    event.resultFullSize = event.resultFullSize or event.result_full_size or 0
    event.durationMs = event.durationMs or event.duration_ms
    event.streamChunks = event.streamChunks or event.stream_chunks or {}
    event.status = event.status or "pending"
    return event
end

local function upsert(event)
    event = normalize(event or {})
    local id = event_id(event)
    if id == "" then
        return
    end
    if M.by_id[id] then
        for k, v in pairs(event) do
            M.by_id[id][k] = v
        end
    else
        M.by_id[id] = event
        table.insert(M.events, event)
    end
end

local function duration(event)
    local ms = tonumber(event.durationMs or 0) or 0
    if ms <= 0 then
        return "-"
    end
    if ms < 1000 then
        return tostring(ms) .. "ms"
    end
    return string.format("%.1fs", ms / 1000)
end

local function result_lines(event)
    local lines = {}
    table.insert(lines, "  args:")
    for _, line in ipairs(vim.split(vim.inspect(event.argsFull or {}), "\n", { plain = true })) do
        table.insert(lines, "    " .. line)
    end
    if event.streamChunks and #event.streamChunks > 0 then
        table.insert(lines, "  stream:")
        local stream = table.concat(event.streamChunks, "")
        for _, line in ipairs(vim.split(stream, "\n", { plain = true })) do
            if line ~= "" then
                table.insert(lines, "    " .. line)
            end
        end
    end
    local result = tostring(event.resultFull or event.resultPreview or "")
    if result ~= "" then
        table.insert(lines, "  result:")
        for _, line in ipairs(vim.split(result, "\n", { plain = true })) do
            table.insert(lines, "    " .. line)
        end
    end
    if event.error and event.error ~= "" then
        table.insert(lines, "  error: " .. tostring(event.error))
    end
    return lines
end

local function row(event)
    local status = tostring(event.status or "pending")
    local glyph = glyphs[status] or "?"
    local dismissed = event.dismissed and " dismissed" or ""
    return table.concat({
        pad(glyph .. " " .. status .. dismissed, M.widths.status),
        pad(duration(event), M.widths.duration),
        pad(event.toolName or "tool", M.widths.tool),
        truncate(event.argsPreview or "", M.widths.args),
    }, " ")
end

function M.render()
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then
        return
    end
    local lines = { "Agent Timeline", "status     duration tool               args", string.rep("-", 92) }
    M.line_events = {}
    local last_turn = nil
    for _, event in ipairs(M.events) do
        local tid = turn_id(event)
        if tid ~= last_turn then
            last_turn = tid
            table.insert(lines, "")
            table.insert(lines, "turn " .. (tid ~= "" and tid or "?"))
        end
        table.insert(lines, row(event))
        M.line_events[#lines] = event_id(event)
        if M.expanded[event_id(event)] then
            for _, line in ipairs(result_lines(event)) do
                table.insert(lines, line)
                M.line_events[#lines] = event_id(event)
            end
        end
    end
    if #M.events == 0 then
        table.insert(lines, "no tool events")
    end
    vim.bo[M.buf].modifiable = true
    vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, lines)
    vim.bo[M.buf].modifiable = false
end

local function current_event()
    local rownum = vim.api.nvim_win_get_cursor(0)[1]
    local id = M.line_events[rownum]
    if not id then
        return nil
    end
    return M.by_id[id]
end

local function request_action(method, event, cb)
    if not event then
        return
    end
    rpc.request(method, { eventId = event_id(event) }, function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] timeline: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end
            if type(cb) == "function" then
                cb(result)
            end
            M.refresh()
        end)
    end)
end

function M.toggle_expand()
    local event = current_event()
    if not event then
        return
    end
    local id = event_id(event)
    M.expanded[id] = not M.expanded[id]
    M.render()
end

function M.cancel_current()
    request_action("timeline.cancel", current_event())
end

function M.retry_current()
    request_action("timeline.retry", current_event())
end

function M.dismiss_current()
    request_action("timeline.dismiss", current_event())
end

function M.goto_event(delta)
    local cur = vim.api.nvim_win_get_cursor(0)[1]
    local step = delta > 0 and 1 or -1
    local line = cur + step
    while line >= 1 and line <= vim.api.nvim_buf_line_count(M.buf) do
        if M.line_events[line] then
            vim.api.nvim_win_set_cursor(0, { line, 0 })
            return
        end
        line = line + step
    end
end

function M.goto_file()
    local event = current_event()
    if not event then
        return
    end
    local args = event.argsFull or {}
    local path = args.path or args.file_path or args.file or args.filename
    if path and path ~= "" then
        vim.cmd("edit " .. vim.fn.fnameescape(tostring(path)))
    end
end

local function bind(buf, lhs, fn)
    vim.keymap.set("n", lhs, fn, { buffer = buf, silent = true, nowait = true })
end

function M.open()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_set_current_win(M.win)
        M.refresh()
        return M.buf
    end
    M.buf = vim.api.nvim_create_buf(false, true)
    vim.bo[M.buf].buftype = "nofile"
    vim.bo[M.buf].bufhidden = "wipe"
    vim.bo[M.buf].swapfile = false
    vim.bo[M.buf].filetype = "poor-cli-timeline"
    vim.api.nvim_buf_set_name(M.buf, "[poor-cli timeline]")
    local float_win = require("poor-cli.float_win")
    M.win = float_win.open(M.buf, {
        width = math.min(100, vim.o.columns - 4),
        height = math.max(20, vim.o.lines - 4),
        position = "center",
        title = " poor-cli timeline ",
        close_keys = {},
    })
    bind(M.buf, "q", M.close)
    bind(M.buf, "<Esc>", M.close)
    bind(M.buf, "<CR>", M.toggle_expand)
    bind(M.buf, "gc", M.cancel_current)
    bind(M.buf, "gr", M.retry_current)
    bind(M.buf, "gd", M.dismiss_current)
    bind(M.buf, "gj", function() M.goto_event(1) end)
    bind(M.buf, "gk", function() M.goto_event(-1) end)
    bind(M.buf, "gf", M.goto_file)
    bind(M.buf, "r", M.refresh)
    M.refresh()
    return M.buf
end

function M.close()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_win_close(M.win, true)
    end
    M.win = nil
end

function M.toggle()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        M.close()
    else
        M.open()
    end
end

function M.refresh()
    rpc.request("timeline.list", { limit = 200 }, function(result, err)
        vim.schedule(function()
            if err then
                if M.buf and vim.api.nvim_buf_is_valid(M.buf) then
                    vim.bo[M.buf].modifiable = true
                    vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, { "Agent Timeline", rpc.format_error(err) })
                    vim.bo[M.buf].modifiable = false
                end
                return
            end
            M.events = {}
            M.by_id = {}
            for _, event in ipairs((result or {}).events or {}) do
                upsert(event)
            end
            M.render()
        end)
    end)
end

function M.handle_event(event)
    upsert(event)
    M.render()
end

function M.handle_chunk(data, append_fn)
    local event_id_value = tostring(data.event_id or data.eventId or "")
    local state = state_for(event_id_value)
    local index = tonumber(data.chunk_index or data.chunkIndex or 0) or 0
    state.pending[index] = tostring(data.chunk or "")

    while state.pending[state.next_index] ~= nil do
        local chunk = state.pending[state.next_index]
        state.pending[state.next_index] = nil
        if chunk ~= "" and type(append_fn) == "function" then
            append_fn(chunk, data)
        end
        local event = M.by_id[event_id_value]
        if event and chunk ~= "" then
            event.streamChunks = event.streamChunks or {}
            table.insert(event.streamChunks, chunk)
        end
        state.next_index = state.next_index + 1
        state.chunks_processed = state.next_index
    end
    ack(event_id_value, state.chunks_processed)
    M.render()
end

function M.reset(event_id_value)
    if event_id_value then
        M.streams[tostring(event_id_value)] = nil
    else
        M.streams = {}
    end
end

function M.setup()
    if M._setup_done then
        return
    end
    M._setup_done = true
    local group = vim.api.nvim_create_augroup("poor-cli-timeline", { clear = true })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLITimelineEvent",
        callback = function(ev)
            vim.schedule(function()
                M.handle_event(ev.data or {})
            end)
        end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLIToolChunk",
        callback = function(ev)
            local data = ev.data or {}
            vim.schedule(function()
                M.handle_chunk(data)
            end)
        end,
    })
end

M.setup()

return M
