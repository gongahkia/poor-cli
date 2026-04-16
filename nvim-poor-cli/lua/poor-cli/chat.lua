-- poor-cli/chat.lua
-- Chat panel for AI conversations

local config = require("poor-cli.config")
local rpc = require("poor-cli.rpc")
local diagnostics = require("poor-cli.diagnostics")
local timeline = require("poor-cli.timeline")
local pickers = require("poor-cli.pickers")
local mentions = require("poor-cli.mentions")
local attribution = require("poor-cli.chat_attribution")

local M = {}

M.buf = nil
M.win = nil
M.history = {}
M.input_buf = nil
M.input_win = nil
M.loading_ns = vim.api.nvim_create_namespace("poor-cli-chat-loading")
M.cost_ns = vim.api.nvim_create_namespace("poor-cli-chat-cost")
M.branch_ns = vim.api.nvim_create_namespace("poor-cli-chat-branches")
M.edit_ns = vim.api.nvim_create_namespace("poor-cli-chat-edit")
M.diff_ns = vim.api.nvim_create_namespace("poor-cli-chat-diff") -- fallback +/- highlights when treesitter unavailable

local function highlight_diff_block(buf, first_line, last_line)
    if not buf or not vim.api.nvim_buf_is_valid(buf) then return end
    local lines = vim.api.nvim_buf_get_lines(buf, first_line, last_line, false)
    local in_fence = false
    for i, line in ipairs(lines) do
        local row = first_line + i - 1
        if not in_fence then
            if line:match("^%s*```diff%s*$") then in_fence = true end
        else
            if line:match("^%s*```%s*$") then
                in_fence = false
            else
                local hl
                if line:match("^%+%+%+") or line:match("^%-%-%-") then
                    hl = "DiffFile"
                elseif line:sub(1, 1) == "+" then
                    hl = "DiffAdd"
                elseif line:sub(1, 1) == "-" then
                    hl = "DiffDelete"
                elseif line:sub(1, 2) == "@@" then
                    hl = "DiffChange"
                end
                if hl then
                    pcall(vim.api.nvim_buf_set_extmark, buf, M.diff_ns, row, 0, { line_hl_group = hl, priority = 80 })
                end
            end
        end
    end
end

M._highlight_diff_block = highlight_diff_block -- exposed for tests

-- Chat-turn tracing. Controlled by config.chat_trace = "off"|"basic"|"verbose".
-- "basic" surfaces the 3 turn boundaries (sent / first-token / done) as
-- user-visible toasts; "verbose" adds thinking-start and thinking-end
-- markers. See the :PoorCLIChatTrace command below for a runtime switch.
local function _chat_trace_mode()
    local ok, cfg = pcall(require, "poor-cli.config")
    if not ok or type(cfg.get) ~= "function" then return "off" end
    local mode = cfg.get("chat_trace")
    if mode == "basic" or mode == "verbose" then return mode end
    return "off"
end

local function chat_trace(level, msg)
    local mode = _chat_trace_mode()
    if mode == "off" then return end
    if level == "verbose" and mode ~= "verbose" then return end
    local ok, notify = pcall(require, "poor-cli.notify")
    if ok then notify.notify("[poor-cli trace] " .. msg, vim.log.levels.INFO, { title = "poor-cli trace" }) end
end

local function _ms_since(started_ns)
    if not started_ns or started_ns == 0 or not vim.loop.hrtime then return 0 end
    return math.floor((vim.loop.hrtime() - started_ns) / 1000000)
end

-- Does the active provider declare EXTENDED_THINKING? Returns (bool, label)
-- where label is "<provider>/<model>" for use in the warning. Unknown /
-- unconfigured providers return (nil, label) so callers can treat "no
-- initialize yet" separately from "confirmed unsupported".
local function _provider_supports_thinking()
    local caps = rpc.get_capabilities() or {}
    local info = caps.providerInfo or {}
    local pc = info.capabilities or {}
    local name = tostring(info.name or "?")
    local model = tostring(info.model or "?")
    local label = name .. "/" .. model
    if next(pc) == nil then return nil, label end
    return pc.extended_thinking == true, label
end

-- Fire a "verbose thinking not supported" nudge once per (provider, model).
-- Resets when the provider/model changes so a :PoorCLISwitchProvider picks
-- up a thinking-capable model cleanly.
M._thinking_unsupported_nudge = { key = nil }
local function _warn_thinking_unsupported_once()
    local supported, label = _provider_supports_thinking()
    if supported ~= false then return end
    if M._thinking_unsupported_nudge.key == label then return end
    M._thinking_unsupported_nudge.key = label
    require("poor-cli.notify").notify(
        "[poor-cli] chat_trace=verbose but " .. label .. " does not emit "
        .. "chain-of-thought. Basic traces still fire. Switch to a reasoning-capable "
        .. "model (e.g. :PoorCLISwitchProvider anthropic claude-sonnet-4-20250514) for "
        .. "thinking brackets.",
        vim.log.levels.WARN,
        { title = "poor-cli trace" }
    )
end

M._provider_supports_thinking = _provider_supports_thinking -- test hook

M.turns = {}
M.loading_marker = nil
M.streaming_buf_line = nil
M.streaming_request_id = nil
M.streaming_response_text = nil
M.active_stream = nil -- { request_id, rpc_request_id }
M.message_queue = {} -- FIFO queue of { message = string, resolved_msg = string, mention_files = {}, context_files = {} }
M.stream_meta = nil -- { started_at_ns, input_tokens, output_tokens, estimated_cost, cache_read, cache_creation }
M.last_non_chat_win = nil
M.edit_state = nil
M.typing_presence = { presence = {}, members = {}, localConnectionId = "" }
M._typing_footer = { buf = nil, win = nil, text = nil }
M._local_typing = { typing = false, last_true_ms = 0, idle_timer = nil }

M.register_source = mentions.register_source

local function chat_header_lines()
    return {
        "# poor-cli Chat",
        "",
        "Use `:PoorCLISend` or press `<CR>` at the bottom to send a message.",
        "Share: press `S` or run `:PoorCLICollabQuick` to copy a prompter invite.",
        "",
        "---",
        "",
    }
end

local function notify_no_codeblock()
    require("poor-cli.notify").notify("[poor-cli] no fenced code block under cursor", vim.log.levels.INFO)
end

local function is_chat_buf(buf)
    return M.buf and buf == M.buf
end

local function is_target_buf(buf)
    if not buf or not vim.api.nvim_buf_is_valid(buf) or is_chat_buf(buf) then
        return false
    end
    if vim.bo[buf].buftype ~= "" then
        return false
    end
    return vim.api.nvim_buf_get_name(buf) ~= ""
end

local function remember_current_target_win()
    local win = vim.api.nvim_get_current_win()
    local buf = vim.api.nvim_win_get_buf(win)
    if is_target_buf(buf) then
        M.last_non_chat_win = win
    end
end

local function setup_target_window_tracking()
    local group = vim.api.nvim_create_augroup("poor-cli-chat-target-window", { clear = true })
    vim.api.nvim_create_autocmd("WinEnter", {
        group = group,
        callback = remember_current_target_win,
    })
end

setup_target_window_tracking()

local function trim(value)
    return tostring(value or ""):gsub("^%s+", ""):gsub("%s+$", "")
end

local function now_ms()
    local uv = vim.uv or vim.loop
    return uv and uv.now and uv.now() or math.floor(os.clock() * 1000)
end

local function multiplayer_state()
    if type(rpc.get_multiplayer_state) ~= "function" then return {} end
    return rpc.get_multiplayer_state() or {}
end

local function multiplayer_active()
    local state = multiplayer_state()
    return state.enabled == true or trim(state.room) ~= ""
end

local function local_connection_id()
    local state = multiplayer_state()
    return trim(state.local_connection_id or state.localConnectionId)
end

local function remote_author_prefix(event)
    if not multiplayer_active() or type(event) ~= "table" then return "" end
    local author_id = trim(event.authorConnectionId or event.author_connection_id)
    if author_id == "" then return "" end
    local local_id = local_connection_id()
    if local_id ~= "" and author_id == local_id then return "" end
    if author_id == "local" then return "" end
    return attribution.format_author(event)
end

local function message_header(role, event)
    local prefix = remote_author_prefix(event)
    if prefix ~= "" then
        return "## " .. prefix
    end
    if role == "user" then
        return "## 👤 You"
    end
    return "## 🤖 Assistant"
end

local function parse_fence_lang(line)
    local info = line:match("^%s*`+%s*(.*)$") or line:match("^%s*~+%s*(.*)$") or ""
    return (trim(info):match("^([^%s]+)") or ""):gsub("[^%w_+%-%.#]", "")
end

local function ensure_markdown_parser(buf)
    if not vim.treesitter or not vim.treesitter.get_parser or not vim.treesitter.get_node then
        return false
    end
    local ok, parser = pcall(vim.treesitter.get_parser, buf, "markdown")
    if not ok or not parser then
        return false
    end
    pcall(function() parser:parse() end)
    return true
end

function M.codeblock_under_cursor()
    local buf = vim.api.nvim_get_current_buf()
    if not ensure_markdown_parser(buf) then
        return nil
    end
    local cursor = vim.api.nvim_win_get_cursor(0)
    local row = math.max(cursor[1] - 1, 0)
    local col = math.max(cursor[2], 0)
    local ok, node = pcall(vim.treesitter.get_node, {
        bufnr = buf,
        pos = { row, col },
        lang = "markdown",
        ignore_injections = true,
    })
    if (not ok or not node) and col > 0 then
        ok, node = pcall(vim.treesitter.get_node, {
            bufnr = buf,
            pos = { row, col - 1 },
            lang = "markdown",
            ignore_injections = true,
        })
    end
    if not ok or not node then
        return nil
    end
    while node and node:type() ~= "fenced_code_block" do
        node = node:parent()
    end
    if not node then
        return nil
    end
    local start_row, _, end_row = node:range()
    local lines = vim.api.nvim_buf_get_lines(buf, start_row, end_row, false)
    if #lines < 2 then
        return nil
    end
    local body_lines = {}
    local last = #lines
    if not lines[last]:match("^%s*`+") and not lines[last]:match("^%s*~+") then
        last = last + 1
    end
    for index = 2, last - 1 do
        table.insert(body_lines, lines[index] or "")
    end
    local lang = parse_fence_lang(lines[1])
    return {
        body = table.concat(body_lines, "\n"),
        lang = lang ~= "" and lang or "text",
        start_row = start_row,
        end_row = end_row,
    }
end

function M.yank_codeblock()
    local block = M.codeblock_under_cursor()
    if not block then
        notify_no_codeblock()
        return false
    end
    vim.fn.setreg('"', block.body)
    if vim.o.clipboard:find("unnamedplus", 1, true) then
        pcall(vim.fn.setreg, "+", block.body)
    elseif vim.o.clipboard:find("unnamed", 1, true) then
        pcall(vim.fn.setreg, "*", block.body)
    end
    require("poor-cli.notify").notify("[poor-cli] yanked code block", vim.log.levels.INFO)
    return true
end

function M.open_codeblock_scratch()
    local block = M.codeblock_under_cursor()
    if not block then
        notify_no_codeblock()
        return false
    end
    vim.cmd("rightbelow split")
    local buf = vim.api.nvim_create_buf(false, true)
    vim.bo[buf].buftype = "nofile"
    vim.bo[buf].bufhidden = "wipe"
    vim.bo[buf].swapfile = false
    vim.bo[buf].filetype = block.lang
    vim.api.nvim_buf_set_name(buf, "[poor-cli codeblock]")
    vim.api.nvim_win_set_buf(0, buf)
    vim.api.nvim_buf_set_lines(buf, 0, -1, false, vim.split(block.body, "\n", { plain = true }))
    return true
end

local function buffer_text(buf)
    local text = table.concat(vim.api.nvim_buf_get_lines(buf, 0, -1, false), "\n")
    if vim.bo[buf].endofline then
        text = text .. "\n"
    end
    return text
end

local function replace_buffer_text(buf, text)
    local lines = vim.split(text, "\n", { plain = true })
    if text:sub(-1) == "\n" then
        table.remove(lines)
    end
    vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
end

local function target_cursor(buf, win)
    if win and vim.api.nvim_win_is_valid(win) and vim.api.nvim_win_get_buf(win) == buf then
        return vim.api.nvim_win_get_cursor(win)
    end
    for _, candidate in ipairs(vim.fn.win_findbuf(buf)) do
        if vim.api.nvim_win_is_valid(candidate) then
            return vim.api.nvim_win_get_cursor(candidate)
        end
    end
    return { vim.api.nvim_buf_line_count(buf), 0 }
end

local function insert_at_cursor_text(buf, win, text)
    local original = buffer_text(buf)
    local lines = vim.api.nvim_buf_get_lines(buf, 0, -1, false)
    local cursor = target_cursor(buf, win)
    local row = math.max(cursor[1], 1)
    local col = math.max(cursor[2], 0)
    while #lines < row do
        table.insert(lines, "")
    end
    local current = lines[row] or ""
    local before = current:sub(1, col)
    local after = current:sub(col + 1)
    local block_lines = vim.split(text, "\n", { plain = true })
    if text:sub(-1) == "\n" then
        table.remove(block_lines)
    end
    if #block_lines == 0 then
        block_lines = { "" }
    end
    block_lines[1] = before .. block_lines[1]
    block_lines[#block_lines] = block_lines[#block_lines] .. after
    lines[row] = block_lines[1]
    for index = 2, #block_lines do
        table.insert(lines, row + index - 1, block_lines[index])
    end
    local proposed = table.concat(lines, "\n")
    if vim.bo[buf].endofline then
        proposed = proposed .. "\n"
    end
    return original, proposed
end

local function diff_review_should_handle(path, original, proposed)
    if original == proposed then
        return false
    end
    if trim(vim.env.POOR_CLI_DIFF_REVIEW):lower() == "auto" then
        return false
    end
    local dr = config.get("diff_review") or {}
    local mode = trim(dr.mode or "review"):lower()
    if mode == "auto" then
        return false
    end
    if mode == "review" or mode == "" then
        return true
    end
    if mode ~= "review_risky" then
        return true
    end
    local basename = vim.fn.fnamemodify(path, ":t")
    for _, pattern in ipairs(dr.risky_paths or {}) do
        local ok, matched = pcall(string.match, tostring(path), tostring(pattern))
        if pattern == path or pattern == basename or (ok and matched) then
            return true
        end
    end
    local changed = 0
    local diff = vim.diff(original, proposed, { result_type = "unified" }) or ""
    for line in diff:gmatch("[^\n]+") do
        if line:match("^[+-]") and not line:match("^%+%+%+") and not line:match("^%-%-%-") then
            changed = changed + 1
        end
    end
    return changed >= tonumber(dr.risky_line_threshold or 50)
end

local function choose_target(callback)
    local win = M.last_non_chat_win
    if win and vim.api.nvim_win_is_valid(win) and is_target_buf(vim.api.nvim_win_get_buf(win)) then
        callback({ win = win, buf = vim.api.nvim_win_get_buf(win), path = vim.api.nvim_buf_get_name(vim.api.nvim_win_get_buf(win)) })
        return
    end
    local choices = {}
    for _, buf in ipairs(vim.api.nvim_list_bufs()) do
        if vim.api.nvim_buf_is_loaded(buf) and is_target_buf(buf) then
            table.insert(choices, { buf = buf, path = vim.api.nvim_buf_get_name(buf) })
        end
    end
    if #choices == 0 then
        require("poor-cli.notify").notify("[poor-cli] no target file buffer", vim.log.levels.INFO)
        callback(nil)
        return
    end
    vim.ui.select(choices, {
        prompt = "Apply code block to buffer:",
        format_item = function(item) return item.path end,
    }, function(choice)
        if choice then
            callback({ buf = choice.buf, path = choice.path })
        else
            callback(nil)
        end
    end)
end

local function direct_confirm_write(target, proposed)
    vim.ui.input({ prompt = "Write code block to " .. target.path .. "? type yes: " }, function(answer)
        if trim(answer):lower() ~= "yes" then
            require("poor-cli.notify").notify("[poor-cli] write cancelled", vim.log.levels.INFO)
            return
        end
        local was_modifiable = vim.bo[target.buf].modifiable
        vim.bo[target.buf].modifiable = true
        replace_buffer_text(target.buf, proposed)
        vim.bo[target.buf].modifiable = was_modifiable
        vim.api.nvim_buf_call(target.buf, function()
            vim.cmd("write!")
        end)
        require("poor-cli.notify").notify("[poor-cli] wrote code block", vim.log.levels.INFO)
    end)
end

function M.apply_codeblock()
    local block = M.codeblock_under_cursor()
    if not block then
        notify_no_codeblock()
        return false
    end
    choose_target(function(target)
        if not target then
            return
        end
        local original, proposed = insert_at_cursor_text(target.buf, target.win or vim.api.nvim_get_current_win(), block.body)
        if diff_review_should_handle(target.path, original, proposed) then
            local ok, diff_review = pcall(require, "poor-cli.diff_review")
            if ok and type(diff_review.stage_codeblock) == "function" then
                diff_review.stage_codeblock({
                    path = target.path,
                    original = original,
                    proposed = proposed,
                    prompt = "chat fenced code block",
                    filetype = block.lang,
                })
                return
            end
        end
        direct_confirm_write(target, proposed)
    end)
    return true
end

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
        vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, chat_header_lines())
        M._refresh_liveness()
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
    M.refresh_typing_presence()
    local ok_pin, turn_pin = pcall(require, "poor-cli.turn_pin")
    if ok_pin then
        pcall(turn_pin.install_keymaps, M.buf)
        pcall(turn_pin.hydrate)
    end
end

local typing_footer_close

function M.close()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_win_close(M.win, true)
        M.win = nil
    end
    if typing_footer_close then typing_footer_close() end
end

typing_footer_close = function()
    local footer = M._typing_footer
    if footer.win and vim.api.nvim_win_is_valid(footer.win) then
        vim.api.nvim_win_close(footer.win, true)
    end
    footer.win = nil
    if footer.buf and vim.api.nvim_buf_is_valid(footer.buf) then
        vim.api.nvim_buf_delete(footer.buf, { force = true })
    end
    footer.buf = nil
    footer.text = nil
    local ip = M._input_popup
    if ip and ip.win and vim.api.nvim_win_is_valid(ip.win) and M.win and vim.api.nvim_win_is_valid(M.win) then
        local pos = vim.api.nvim_win_get_position(M.win)
        pcall(vim.api.nvim_win_set_config, ip.win, { relative = "editor", row = pos[1] + vim.api.nvim_win_get_height(M.win) - 1, col = pos[2] + 1 })
    end
end

local function render_typing_footer()
    local state = multiplayer_state()
    M.typing_presence.localConnectionId = state.local_connection_id or state.localConnectionId or M.typing_presence.localConnectionId or ""
    M.typing_presence.members = state.members or M.typing_presence.members or {}
    local text = attribution.format_typing_footer(M.typing_presence)
    if not text then
        typing_footer_close()
        return
    end
    if not M.win or not vim.api.nvim_win_is_valid(M.win) then
        return
    end
    local footer = M._typing_footer
    if not footer.buf or not vim.api.nvim_buf_is_valid(footer.buf) then
        footer.buf = vim.api.nvim_create_buf(false, true)
        vim.bo[footer.buf].buftype = "nofile"
        vim.bo[footer.buf].bufhidden = "wipe"
        vim.bo[footer.buf].swapfile = false
    end
    if footer.text ~= text then
        vim.api.nvim_buf_set_lines(footer.buf, 0, -1, false, { " " .. text })
        footer.text = text
    end
    local width = math.max(20, vim.api.nvim_win_get_width(M.win) - 2)
    local pos = vim.api.nvim_win_get_position(M.win)
    local row = pos[1] + vim.api.nvim_win_get_height(M.win) - 1
    local col = pos[2] + 1
    local ip = M._input_popup
    if ip and ip.win and vim.api.nvim_win_is_valid(ip.win) then
        pcall(vim.api.nvim_win_set_config, ip.win, { relative = "editor", row = math.max(0, row - 2), col = col })
    end
    if footer.win and vim.api.nvim_win_is_valid(footer.win) then
        pcall(vim.api.nvim_win_set_config, footer.win, {
            relative = "editor",
            width = width,
            height = 1,
            row = row,
            col = col,
            style = "minimal",
            focusable = false,
            zindex = 54,
        })
        return
    end
    footer.win = vim.api.nvim_open_win(footer.buf, false, {
        relative = "editor",
        width = width,
        height = 1,
        row = row,
        col = col,
        style = "minimal",
        focusable = false,
        zindex = 54,
    })
    if footer.win and vim.api.nvim_win_is_valid(footer.win) then
        vim.wo[footer.win].winblend = 10
    end
end

function M.toggle()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        M.close()
    else
        M.open()
    end
end

local function branch_badge(turn)
    local count = tonumber(turn and (turn.siblingCount or turn.sibling_count)) or 0
    local index = tonumber(turn and (turn.siblingIndex or turn.sibling_index)) or 0
    if count <= 1 or index <= 0 then return "" end
    return string.format("[branch %d/%d]", index, count)
end

local function record_turn_extmark(role, start_line, end_line, turn, content)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then return end
    turn = turn or {}
    local turn_id = turn.id or turn.turnId or turn.turn_id
    local index = #M.history + 1
    local meta = {
        id = turn_id,
        role = role,
        content = content or "",
        index = index,
        start_line = start_line,
        end_line = end_line,
        parentId = turn.parentId or turn.parent_id,
        branchOf = turn.branchOf or turn.branch_of,
        siblingIndex = turn.siblingIndex or turn.sibling_index,
        siblingCount = turn.siblingCount or turn.sibling_count,
    }
    table.insert(M.turns, meta)
    local opts = { end_row = end_line, end_col = 0, invalidate = true, right_gravity = false }
    local badge = branch_badge(meta)
    if badge ~= "" then
        opts.virt_text = { { " " .. badge, "Comment" } }
        opts.virt_text_pos = "eol"
        opts.hl_mode = "combine"
    end
    pcall(vim.api.nvim_buf_set_extmark, M.buf, M.branch_ns, start_line, 0, opts)
end

function M.append_message(role, content, turn)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end

    local lines = { message_header(role, turn) }

    table.insert(lines, "")
    for _, line in ipairs(vim.split(content, "\n", { plain = true })) do
        table.insert(lines, line)
    end
    table.insert(lines, "")
    table.insert(lines, "---")
    table.insert(lines, "")

    local line_count = vim.api.nvim_buf_line_count(M.buf)
    vim.api.nvim_buf_set_lines(M.buf, line_count, line_count, false, lines)
    record_turn_extmark(role, line_count, line_count + #lines, turn, content)
    if role == "assistant" then M._set_assistant_badge(line_count) end
    local ok_pin, turn_pin = pcall(require, "poor-cli.turn_pin")
    if ok_pin then pcall(turn_pin.render) end

    if M.win and vim.api.nvim_win_is_valid(M.win) then
        local new_count = vim.api.nvim_buf_line_count(M.buf)
        vim.api.nvim_win_set_cursor(M.win, { new_count, 0 })
    end

    table.insert(M.history, {
        role = role,
        content = content,
        id = turn and (turn.id or turn.turnId or turn.turn_id) or nil,
        parentId = turn and (turn.parentId or turn.parent_id) or nil,
        branchOf = turn and (turn.branchOf or turn.branch_of) or nil,
        authorConnectionId = turn and (turn.authorConnectionId or turn.author_connection_id) or nil,
        authorDisplayName = turn and (turn.authorDisplayName or turn.author_display_name) or nil,
    })
    if role == "assistant" then
        diagnostics.apply_from_text(content)
    end
end

local function history_content(message)
    if type(message.content) == "string" then
        return message.content
    end
    if type(message.parts) == "table" then
        local parts = {}
        for _, part in ipairs(message.parts) do
            if type(part) == "string" then
                table.insert(parts, part)
            elseif type(part) == "table" and type(part.text) == "string" then
                table.insert(parts, part.text)
            end
        end
        return table.concat(parts, "\n")
    end
    return ""
end

local function history_meta(message, turn)
    local meta = type(turn) == "table" and vim.deepcopy(turn) or {}
    if type(message) ~= "table" then return meta end
    local author = type(message.author) == "table" and message.author or {}
    meta.authorConnectionId = message.authorConnectionId or message.author_connection_id or author.authorConnectionId or author.author_connection_id or meta.authorConnectionId
    meta.authorDisplayName = message.authorDisplayName or message.author_display_name or author.authorDisplayName or author.author_display_name or meta.authorDisplayName
    meta.authorRole = message.authorRole or message.author_role or author.authorRole or author.author_role or meta.authorRole
    return meta
end

local function history_role(message)
    local role = tostring(message.role or "assistant")
    if role == "model" then return "assistant" end
    return role
end

function M.render_history(messages, branch_payload)
    M.open()
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then return end
    vim.api.nvim_buf_clear_namespace(M.buf, M.branch_ns, 0, -1)
    vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, chat_header_lines())
    M.history = {}
    M.turns = {}
    local active_path = type(branch_payload) == "table" and branch_payload.activePath or {}
    for idx, message in ipairs(messages or {}) do
        M.append_message(history_role(message), history_content(message), history_meta(message, active_path[idx] or message))
    end
end

local function turn_under_cursor()
    if not M.win or not vim.api.nvim_win_is_valid(M.win) then return nil end
    local row = vim.api.nvim_win_get_cursor(M.win)[1] - 1
    for _, turn in ipairs(M.turns or {}) do
        if row >= turn.start_line and row < turn.end_line then
            return turn
        end
    end
    return nil
end

local function clear_edit_state()
    if M.buf and vim.api.nvim_buf_is_valid(M.buf) then
        vim.api.nvim_buf_clear_namespace(M.buf, M.edit_ns, 0, -1)
    end
    M.edit_state = nil
end

local function trim_for_edit(state)
    local index = tonumber(state and state.index) or 0
    local start_line = tonumber(state and state.start_line) or -1
    if index <= 0 or start_line < 0 then return end
    if M.buf and vim.api.nvim_buf_is_valid(M.buf) then
        vim.api.nvim_buf_set_lines(M.buf, start_line, -1, false, {})
        vim.api.nvim_buf_clear_namespace(M.buf, M.branch_ns, start_line, -1)
        vim.api.nvim_buf_clear_namespace(M.buf, M.cost_ns, start_line, -1)
        vim.api.nvim_buf_clear_namespace(M.buf, M.edit_ns, start_line, -1)
    end
    while #M.history >= index do table.remove(M.history) end
    while #M.turns >= index do table.remove(M.turns) end
end

function M.refresh_branch_metadata()
    if not rpc.is_running() then return end
    rpc.chat_siblings({}, function(result, err)
        vim.schedule(function()
            if err or type(result) ~= "table" then return end
            M.apply_branch_metadata(result)
        end)
    end)
end

function M.apply_branch_metadata(branch_payload)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then return end
    local active_path = type(branch_payload) == "table" and branch_payload.activePath or {}
    if type(active_path) ~= "table" or #active_path == 0 then return end
    vim.api.nvim_buf_clear_namespace(M.buf, M.branch_ns, 0, -1)
    for idx, turn in ipairs(M.turns or {}) do
        local meta = active_path[idx]
        if meta then
            turn.id = meta.id or turn.id
            turn.parentId = meta.parentId or meta.parent_id or turn.parentId
            turn.branchOf = meta.branchOf or meta.branch_of or turn.branchOf
            turn.siblingIndex = meta.siblingIndex or meta.sibling_index
            turn.siblingCount = meta.siblingCount or meta.sibling_count
            if M.history[idx] then
                M.history[idx].id = turn.id
                M.history[idx].parentId = turn.parentId
                M.history[idx].branchOf = turn.branchOf
            end
            local opts = { end_row = turn.end_line, end_col = 0, invalidate = true, right_gravity = false }
            local badge = branch_badge(turn)
            if badge ~= "" then
                opts.virt_text = { { " " .. badge, "Comment" } }
                opts.virt_text_pos = "eol"
                opts.hl_mode = "combine"
            end
            pcall(vim.api.nvim_buf_set_extmark, M.buf, M.branch_ns, turn.start_line, 0, opts)
        end
    end
end

local function apply_branch_result(result)
    if type(result) ~= "table" or type(result.snapshot) ~= "table" then return end
    M.render_history(result.snapshot, result)
end

function M.regenerate_turn()
    local turn = turn_under_cursor()
    if not turn or turn.role ~= "assistant" or not turn.id then
        require("poor-cli.notify").notify("[poor-cli] Put cursor on an assistant turn with branch metadata", vim.log.levels.WARN)
        return
    end
    rpc.chat_regenerate({ turnId = turn.id }, function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] regenerate: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end
            apply_branch_result(result)
        end)
    end)
end

function M.switch_sibling(direction)
    local turn = turn_under_cursor()
    local params = { direction = direction }
    if turn and turn.id then params.branchId = turn.id end
    rpc.chat_switch(params, function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] branch switch: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end
            apply_branch_result(result)
        end)
    end)
end

function M.edit_resend_turn()
    if M.active_stream then
        require("poor-cli.notify").notify("[poor-cli] finish or cancel the active response first", vim.log.levels.WARN)
        return
    end
    local turn = turn_under_cursor()
    if not turn or turn.role ~= "user" then
        require("poor-cli.notify").notify("[poor-cli] Put cursor on a user turn", vim.log.levels.WARN)
        return
    end
    if not turn.id then
        require("poor-cli.notify").notify("[poor-cli] user turn has no branch metadata", vim.log.levels.WARN)
        return
    end
    clear_edit_state()
    local state = {
        turn_id = turn.id,
        index = turn.index,
        start_line = turn.start_line,
        content = turn.content or (M.history[turn.index] and M.history[turn.index].content) or "",
    }
    M.edit_state = state
    if M.buf and vim.api.nvim_buf_is_valid(M.buf) then
        pcall(vim.api.nvim_buf_set_extmark, M.buf, M.edit_ns, turn.start_line, 0, {
            virt_text = { { " [editing]", "Comment" } },
            virt_text_pos = "eol",
            hl_mode = "combine",
        })
    end
    M.prompt_and_send({ initial_text = state.content, edit_state = state })
end

local export_formats = {
    { id = "markdown", label = "markdown", rpc_format = "markdown", preview = "Markdown conversation export." },
    { id = "json", label = "json", rpc_format = "json", preview = "Structured JSON conversation export." },
    { id = "transcript", label = "transcript", rpc_format = "transcript", preview = "Plain transcript conversation export." },
}

local function chat_export_config()
    local cfg = config.get("chat_export") or {}
    return {
        dir = cfg.dir or cfg.directory or config.get("export_dir") or vim.fs.joinpath(vim.fn.getcwd(), ".poor-cli", "exports"),
        default_format = cfg.default_format or cfg.default or "markdown",
    }
end

local function export_item(format)
    if format == "md" then format = "markdown" end
    if format == "txt" or format == "text" then format = "transcript" end
    for _, item in ipairs(export_formats) do
        if item.id == format or item.rpc_format == format then return item end
    end
    return export_formats[1]
end

local function export_picker_items()
    local cfg = chat_export_config()
    local default = export_item(cfg.default_format).id
    local items = {}
    for _, item in ipairs(export_formats) do
        if item.id == default then table.insert(items, vim.deepcopy(item)) end
    end
    for _, item in ipairs(export_formats) do
        if item.id ~= default then table.insert(items, vim.deepcopy(item)) end
    end
    return items
end

function M.export_conversation(format)
    local item = export_item(format or chat_export_config().default_format)
    local dir = chat_export_config().dir
    vim.fn.mkdir(dir, "p")
    rpc.export_conversation({ format = item.rpc_format, outputDir = dir }, function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] export: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end
            local path = type(result) == "table" and (result.filePath or result.file_path or result.path) or nil
            require("poor-cli.notify").notify("[poor-cli] exported " .. tostring(path or dir), vim.log.levels.INFO)
        end)
    end)
end

function M.pick_export_format()
    pickers.pick(export_picker_items(), {
        title = "Export Conversation",
        preview = true,
        on_pick = function(data)
            M.export_conversation((data or {}).id)
        end,
    })
end

M._test_export_picker_items = export_picker_items
M._test_chat_export_config = chat_export_config

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
        -- fallback: no chat window open
        require("poor-cli.notify").notify("[poor-cli] " .. content, vim.log.levels.INFO)
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
    local resolved = tostring(message or "")

    resolved = resolved:gsub("@workspace", function()
        local cwd = vim.fn.getcwd()
        local files = scan_workspace_files(cwd, 0, {})
        if #files == 0 then
            return "@workspace"
        end
        return "```\n-- Project files:\n" .. table.concat(files, "\n") .. "\n```"
    end)

    return resolved, {}
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
local function dispatch_message(prepared, opts)
    opts = opts or {}
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
        estimated_output_tokens = 0,
        confidence_percent = nil,
        confidence_category = nil,
    }
    M.streaming_request_id = request_id
    M._start_streaming_block()

    local params = {
        message = prepared.resolved_msg,
        contextFiles = prepared.context_files,
        requestId = request_id,
    }
    if opts.edit_turn_id then params.editTurnId = opts.edit_turn_id end

    do
        local status = (rpc.get_status and rpc.get_status()) or {}
        local provider = tostring(status.provider or status.activeProvider or "?")
        local model = tostring(status.model or status.activeModel or "?")
        chat_trace("basic", string.format("→ sent to %s/%s · %d chars · %d context file%s",
            provider, model, #prepared.resolved_msg,
            #prepared.context_files, #prepared.context_files == 1 and "" or "s"))
        if _chat_trace_mode() == "verbose" then
            _warn_thinking_unsupported_once()
        end
    end
    M._thinking_start_traced = false
    local rpc_request_id = rpc.request("poor-cli/chatStreaming", params, function(_result, err)
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

function M.send(message, opts)
    opts = opts or {}
    if not message or message == "" then
        return
    end

    if not rpc.is_running() then
        require("poor-cli.notify").notify("[poor-cli] Server not running", vim.log.levels.WARN)
        return
    end

    -- short-circuit if we already know the API key is invalid: don't spin
    -- up a "Thinking..." placeholder just to fail once the request hits
    -- the provider. Direct the user at the fix command.
    local caps = rpc.get_capabilities() or {}
    local validity = caps.apiKeyValidity or {}
    if validity.status == "invalid" then
        local provider = tostring(validity.provider or "?")
        local reason = tostring(validity.reason or "server rejected the key")
        local lines = {
            string.format("%s API key invalid — run :PoorCLIApiKey to fix", provider),
            reason,
            "",
            "Send blocked. Rotate the key, then retry.",
        }
        require("poor-cli.notify").notify(table.concat(lines, "\n"), vim.log.levels.ERROR, {
            title = "poor-cli",
            timeout = 8000,
        })
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
    dispatch_message(prepared, opts)
end

local function format_thinking_duration(seconds)
    seconds = math.max(0, math.floor(seconds))
    if seconds < 60 then
        return string.format("%d sec", seconds)
    end
    local mins = math.floor(seconds / 60) % 60
    local secs = seconds % 60
    if seconds < 3600 then
        return string.format("%d min %d sec", mins, secs)
    end
    local hrs = math.floor(seconds / 3600)
    return string.format("%d hr %d min %d sec", hrs, mins, secs)
end

-- single-column spinner frames (braille); matches the Claude Code / Codex feel.
-- change this table to swap spinners — e.g. { "|", "/", "-", "\\" } for pure ASCII.
local SPINNER_FRAMES = { "⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏" }
local SPINNER_INTERVAL_MS = 80
-- Flip the streaming placeholder from "Thinking..." to a "no stream for Xs"
-- warning after this many ms of silence. Chosen well below the backend's
-- 300s RPC timeout so users see something suspicious much sooner.
local STALL_THRESHOLD_MS = 15000

local function spinner_frame(tick)
    return SPINNER_FRAMES[(tick % #SPINNER_FRAMES) + 1]
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

local function ensure_stream_meta()
    if M.stream_meta then return end
    M.stream_meta = {
        started_at_ns = vim.loop.hrtime and vim.loop.hrtime() or 0,
        input_tokens = 0,
        output_tokens = 0,
        estimated_cost = 0,
        cache_read = 0,
        cache_creation = 0,
        estimated_output_tokens = 0,
        confidence_percent = nil,
        confidence_category = nil,
    }
end

function M._start_streaming_block(event)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    local line_count = vim.api.nvim_buf_line_count(M.buf)
    local initial_line = string.format("%s Thinking (0 sec)...", spinner_frame(0))
    vim.api.nvim_buf_set_lines(M.buf, line_count, line_count, false, { message_header("assistant", event), "", initial_line, "" })
    M._set_assistant_badge(line_count)
    if M.stream_meta then
        M.stream_meta.assistant_header_line = line_count
    end
    M.streaming_buf_line = line_count + 2
    M._streaming_placeholder_active = true
    M._streaming_placeholder_line = line_count + 3 -- 1-indexed position of the "Thinking" line
    M.streaming_response_text = ""
    M._thinking_buffer = ""

    -- live-update the placeholder until first chunk arrives or finalize fires
    M._thinking_started_ns = (vim.loop.hrtime and vim.loop.hrtime()) or 0
    M._last_stream_chunk_ns = M._thinking_started_ns
    M._thinking_tick = 0
    M._stop_thinking_timer()
    if vim.loop.new_timer then
        M._thinking_timer = vim.loop.new_timer()
        M._thinking_timer:start(SPINNER_INTERVAL_MS, SPINNER_INTERVAL_MS, vim.schedule_wrap(function()
            if not M._streaming_placeholder_active or not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
                M._stop_thinking_timer()
                return
            end
            M._thinking_tick = (M._thinking_tick or 0) + 1
            local elapsed = 0
            if M._thinking_started_ns > 0 and vim.loop.hrtime then
                elapsed = math.max(0, math.floor((vim.loop.hrtime() - M._thinking_started_ns) / 1000000000))
            end
            -- Stall detection: if no chunk has arrived for STALL_THRESHOLD_MS
            -- (default 15s), flip the placeholder from "Thinking..." to a
            -- visible "no stream for Xs" warning so the user knows the
            -- connection may be dead, not just that the model is slow.
            local silent_ms = 0
            if vim.loop.hrtime and M._last_stream_chunk_ns and M._last_stream_chunk_ns > 0 then
                silent_ms = math.max(0, math.floor((vim.loop.hrtime() - M._last_stream_chunk_ns) / 1000000))
            end
            local ln = M._streaming_placeholder_line
            if ln then
                local new_text
                if silent_ms >= STALL_THRESHOLD_MS then
                    new_text = string.format("⚠ no stream for %ds — may be disconnected (check :PoorCLIOpenLog or :PoorCLIStatus)",
                        math.floor(silent_ms / 1000))
                else
                    new_text = string.format("%s Thinking (%s)...",
                        spinner_frame(M._thinking_tick),
                        format_thinking_duration(elapsed))
                end
                pcall(vim.api.nvim_buf_set_lines, M.buf, ln - 1, ln, false, { new_text })
            end
        end))
    end
end

M._spinner_frame = spinner_frame -- test hook
M._spinner_frames = SPINNER_FRAMES

local function start_remote_stream(data)
    if is_active_request(data.request_id or "") then return true end
    local prefix = remote_author_prefix(data)
    if prefix == "" or trim(data.request_id) == "" then return false end
    M.open()
    M.active_stream = { request_id = data.request_id, remote = true }
    M.streaming_request_id = data.request_id
    ensure_stream_meta()
    M._start_streaming_block(data)
    return true
end

function M._append_streaming_chunk(chunk)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    if not M.streaming_buf_line or not chunk or chunk == "" then
        return
    end
    if vim.loop.hrtime then M._last_stream_chunk_ns = vim.loop.hrtime() end

    if M._streaming_placeholder_active then
        -- first real chunk: stop timer, remove Thinking placeholder lines
        local latency_ms = _ms_since(M._thinking_started_ns)
        chat_trace("basic", string.format("← provider responded · first token +%dms", latency_ms))
        if M._thinking_start_traced and M._thinking_buffer and M._thinking_buffer ~= "" then
            chat_trace("verbose", string.format("💭 thinking ended · %d chars across %d line%s",
                #M._thinking_buffer,
                select(2, M._thinking_buffer:gsub("\n", "\n")) + 1,
                M._thinking_buffer:find("\n") and "s" or ""))
        end
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
    if total_tokens <= 0 then
        total_tokens = meta.estimated_output_tokens or 0
    end
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
    local cache_read = meta.cache_read or 0
    local cache_creation = meta.cache_creation or 0
    if cache_read > 0 or cache_creation > 0 then
        cache_str = string.format(" | cache: %d read, %d created", cache_read, cache_creation)
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
    local ended_meta = M.stream_meta and vim.deepcopy(M.stream_meta) or nil
    if ended_meta then
        ended_meta.cost_usd = ended_meta.estimated_cost or 0
        ended_meta.total_tokens = (ended_meta.input_tokens or 0) + (ended_meta.output_tokens or 0)
        if ended_meta.total_tokens <= 0 then
            ended_meta.total_tokens = ended_meta.estimated_output_tokens or 0
        end
        if ended_meta.started_at_ns and vim.loop.hrtime then
            ended_meta.duration_s = math.max(0, (vim.loop.hrtime() - ended_meta.started_at_ns) / 1e9)
            ended_meta.duration_ms = math.floor(ended_meta.duration_s * 1000)
        end
        local ok, cost = pcall(require, "poor-cli.cost")
        local cfg = config.get("cost") or {}
        if ok and cost.enabled() and cfg.show_turn_badges ~= false and ended_meta.assistant_header_line then
            local badge = cost.format_turn_badge(ended_meta)
            if badge ~= "" then
                pcall(vim.api.nvim_buf_set_extmark, M.buf, M.cost_ns, ended_meta.assistant_header_line, 0, {
                    virt_text = { { " " .. badge, "Comment" } },
                    virt_text_pos = "eol",
                    hl_mode = "combine",
                })
            end
        end
        vim.api.nvim_exec_autocmds("User", {
            pattern = "PoorCLITurnEnded",
            data = ended_meta,
        })
        chat_trace("basic", string.format("✓ turn complete · %d tokens · $%.4f · %.1fs",
            ended_meta.total_tokens or 0, ended_meta.cost_usd or 0, ended_meta.duration_s or 0))
    end
    diagnostics.apply_from_text(M.streaming_response_text or "")
    M.streaming_buf_line = nil
    M.streaming_response_text = nil
    M.streaming_request_id = nil
    M.active_stream = nil
    M.stream_meta = nil
    M.refresh_branch_metadata()

    -- drain the next queued message
    vim.schedule(function()
        M._process_queue()
    end)
end

M._thinking_buffer = ""

function M.setup_streaming_autocmds()
    local group = vim.api.nvim_create_augroup("PoorCLIChatStreaming", { clear = true })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLIStatusChanged",
        callback = function() vim.schedule(M._refresh_liveness) end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLIThinkingChunk",
        callback = function(ev)
            local data = ev.data or {}
            if not is_active_request(data.request_id or "") and not start_remote_stream(data) then
                return
            end
            if data.chunk and data.chunk ~= "" then
                if vim.loop.hrtime then M._last_stream_chunk_ns = vim.loop.hrtime() end
                vim.schedule(function()
                    if not M._thinking_start_traced then
                        M._thinking_start_traced = true
                        chat_trace("verbose", "💭 thinking started (chain-of-thought streaming)")
                    end
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
        pattern = "PoorCLIStreamChunk",
        callback = function(ev)
            local data = ev.data or {}
            if not is_active_request(data.request_id or "") and not start_remote_stream(data) then
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
        pattern = "PoorCLIToolEvent",
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
                        M._append_tool_result(data.tool_name, data.tool_result, data.original_size, data.filtered_size)
                    end
                end
            end)
        end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLIToolChunk",
        callback = function(ev)
            local data = ev.data or {}
            if not is_active_request(data.request_id or "") then
                return
            end
            vim.schedule(function()
                timeline.handle_chunk(data, function(chunk, chunk_data)
                    M._append_tool_stream_chunk(chunk_data.tool_name, chunk)
                end)
            end)
        end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLIPermissionReq",
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
        pattern = "PoorCLIPlanReq",
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
        pattern = "PoorCLIProgress",
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
        pattern = "PoorCLICostUpdate",
        callback = function(ev)
            local data = ev.data or {}
            if not is_active_request(data.request_id or "") then
                return
            end
            vim.schedule(function()
                -- accumulate into stream_meta (server may send multiple updates)
                if M.stream_meta then
                    if data.is_estimate then
                        M.stream_meta.estimated_output_tokens = math.max(M.stream_meta.estimated_output_tokens or 0, data.output_tokens or 0)
                        if (data.estimated_cost or 0) > 0 then
                            M.stream_meta.output_tokens = math.max(M.stream_meta.output_tokens or 0, data.output_tokens or 0)
                            M.stream_meta.estimated_cost = M.stream_meta.estimated_cost + (data.estimated_cost or 0)
                        end
                    else
                        M.stream_meta.input_tokens = M.stream_meta.input_tokens + (data.input_tokens or 0)
                        M.stream_meta.output_tokens = M.stream_meta.output_tokens + (data.output_tokens or 0)
                        M.stream_meta.estimated_cost = M.stream_meta.estimated_cost + (data.estimated_cost or 0)
                        M.stream_meta.cache_read = M.stream_meta.cache_read + (data.cache_read_input_tokens or 0)
                        M.stream_meta.cache_creation = M.stream_meta.cache_creation + (data.cache_creation_input_tokens or 0)
                    end
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
        pattern = "PoorCLIRoomEvent",
        callback = function(ev)
            local data = ev.data or {}
            vim.schedule(function()
                if data.event_type == "started" then
                    start_remote_stream(data)
                end
                M._handle_room_event(data)
            end)
        end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLIMemberTyping",
        callback = function(ev)
            local data = ev.data or {}
            vim.schedule(function()
                M._handle_member_typing(data)
            end)
        end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLIMemberRoleUpdated",
        callback = function(ev)
            local data = ev.data or {}
            vim.schedule(function()
                M._handle_member_role_update(data)
            end)
        end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLISuggestion",
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

-- Glob-to-Lua-pattern. Escapes magic chars then turns * into .*
local function _permission_glob_to_pattern(glob)
    local escaped = (glob or ""):gsub("[%^%$%(%)%%%.%[%]%+%-%?]", "%%%0")
    escaped = escaped:gsub("%*", ".*")
    return "^" .. escaped .. "$"
end

-- Check if a permission entry matches a (tool_name, args) pair.
-- Entry format: "name" or "name:glob". Glob matches against vim.inspect(args).
local function _permission_entry_matches(entry, tool_name, args)
    if type(entry) ~= "string" or entry == "" then return false end
    local name, glob = entry:match("^([^:]+):(.+)$")
    if not name then
        return entry == tool_name
    end
    if name ~= tool_name then return false end
    local haystack = type(args) == "table" and vim.inspect(args) or tostring(args or "")
    return haystack:find(_permission_glob_to_pattern(glob)) ~= nil
        or haystack:find(glob:gsub("%*", ".-"), 1, false) ~= nil
end

local function _permission_verdict(tool_name, tool_args)
    local cfg = config.get("permission") or {}
    for _, entry in ipairs(cfg.deny or {}) do
        if _permission_entry_matches(entry, tool_name, tool_args) then
            return "deny", entry
        end
    end
    for _, entry in ipairs(cfg.allow or {}) do
        if _permission_entry_matches(entry, tool_name, tool_args) then
            return "allow", entry
        end
    end
    return "prompt", nil
end

M._permission_entry_matches = _permission_entry_matches -- test hook
M._permission_verdict = _permission_verdict -- test hook

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

    -- Config-driven allow/deny-list bypass. deny wins over allow. Any hit
    -- short-circuits the modal and responds to the server immediately.
    local verdict, matched_entry = _permission_verdict(tool_name, tool_args)
    if verdict == "allow" then
        rpc.notify("poor-cli/permissionRes", { promptId = prompt_id, allowed = true })
        require("poor-cli.notify").notify(
            string.format("[poor-cli] auto-approved %s (matched allow entry: %s)", tool_name, matched_entry),
            vim.log.levels.INFO
        )
        return
    elseif verdict == "deny" then
        rpc.notify("poor-cli/permissionRes", { promptId = prompt_id, allowed = false })
        require("poor-cli.notify").notify(
            string.format("[poor-cli] auto-denied %s (matched deny entry: %s)", tool_name, matched_entry),
            vim.log.levels.WARN
        )
        return
    end

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
    highlight_diff_block(ui.buf, 0, #lines)
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
    require("poor-cli.notify").notify("[poor-cli] " .. summary, vim.log.levels.INFO)
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
    require("poor-cli.notify").notify("[poor-cli] " .. summary, vim.log.levels.INFO)
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
    require("poor-cli.notify").notify("[poor-cli] " .. summary, vim.log.levels.INFO)
    M.open()
    M.append_system_note(summary)
end

function M._handle_member_typing(data)
    if type(data) ~= "table" then return end
    local connection_id = trim(data.connection_id or data.connectionId)
    if connection_id == "" then return end
    M.typing_presence.presence = M.typing_presence.presence or {}
    M.typing_presence.presence[connection_id] = data.typing == true
    M.typing_presence.members = M.typing_presence.members or {}
    M.typing_presence.members[connection_id] = {
        connectionId = connection_id,
        displayName = data.display_name or data.displayName or connection_id,
    }
    render_typing_footer()
end

function M._apply_presence_snapshot(snapshot)
    if type(snapshot) ~= "table" then return end
    local state = multiplayer_state()
    M.typing_presence = {
        presence = type(snapshot.presence) == "table" and snapshot.presence or {},
        members = type(snapshot.members) == "table" and snapshot.members or state.members or {},
        localConnectionId = state.local_connection_id or state.localConnectionId or "",
    }
    render_typing_footer()
end

function M.refresh_typing_presence()
    if not multiplayer_active() or type(rpc.request) ~= "function" or (type(rpc.is_running) == "function" and not rpc.is_running()) then
        return
    end
    local state = multiplayer_state()
    local params = {}
    if trim(state.room) ~= "" then params.room = state.room end
    rpc.request("poor-cli/listPresence", params, function(result, _err)
        vim.schedule(function()
            M._apply_presence_snapshot(result)
        end)
    end)
end

local function typing_debounce_ms()
    local multiplayer = config.get("multiplayer") or {}
    local presence = type(multiplayer) == "table" and multiplayer.typingPresence or {}
    local configured = type(presence) == "table" and tonumber(presence.debounceMs or presence.debounce_ms) or nil
    return math.max(250, configured or 250)
end

local function stop_local_idle_timer()
    local local_state = M._local_typing
    if local_state.idle_timer then
        pcall(function()
            local_state.idle_timer:stop()
            local_state.idle_timer:close()
        end)
        local_state.idle_timer = nil
    end
end

local function send_typing_state(typing, force)
    if not multiplayer_active() or type(rpc.request) ~= "function" then return end
    if type(rpc.is_running) == "function" and not rpc.is_running() then return end
    local local_state = M._local_typing
    local now = now_ms()
    if typing then
        local debounce = typing_debounce_ms()
        if not force and local_state.typing and (now - (local_state.last_true_ms or 0)) < debounce then
            return
        end
        local_state.last_true_ms = now
    elseif not local_state.typing and not force then
        return
    end
    local_state.typing = typing == true
    local mp = multiplayer_state()
    local params = { typing = typing == true }
    if trim(mp.room) ~= "" then params.room = mp.room end
    local id = trim(mp.local_connection_id or mp.localConnectionId)
    if id ~= "" then params.connectionId = id end
    rpc.request("poor-cli/setTyping", params, function() end)
end

local function mark_local_typing()
    send_typing_state(true, false)
    stop_local_idle_timer()
    local uv = vim.uv or vim.loop
    if uv and uv.new_timer then
        M._local_typing.idle_timer = uv.new_timer()
        M._local_typing.idle_timer:start(2000, 0, vim.schedule_wrap(function()
            send_typing_state(false, true)
            stop_local_idle_timer()
        end))
    else
        vim.defer_fn(function()
            send_typing_state(false, true)
        end, 2000)
    end
end

local function clear_local_typing()
    stop_local_idle_timer()
    send_typing_state(false, true)
end

-- Assistant liveness badges. Two surfaces: per-assistant-header virt_text
-- dot, and a sticky virt_text line pinned to line 1. Both read the current
-- rpc.capabilities.apiKeyValidity + rpc.server_state and refresh on the
-- PoorCLIStatusChanged autocmd so the dot flips in place when the provider
-- state changes.
M.liveness_ns = M.liveness_ns or vim.api.nvim_create_namespace("poor-cli-liveness")
M._assistant_header_lines = M._assistant_header_lines or {}  -- list of {row, extmark_id}
M._top_line_extmark = M._top_line_extmark or nil

local function _compute_liveness()
    -- specs often stub rpc with only the fields they exercise; fall back
    -- gracefully when get_capabilities / get_status aren't present on the
    -- stub rather than crashing render.
    local caps = (type(rpc.get_capabilities) == "function" and rpc.get_capabilities()) or rpc.capabilities or {}
    local validity = caps.apiKeyValidity or {}
    local status = (type(rpc.get_status) == "function" and rpc.get_status()) or {}
    local state = tostring(status.state or rpc.server_state or "")

    if validity.status == "invalid" then
        local provider = tostring(validity.provider or caps.providerInfo and caps.providerInfo.name or "?")
        return { icon = "🔴", label = "key invalid (" .. provider .. ")", hl = "ErrorMsg" }
    end
    if state == "error" then
        return { icon = "🔴", label = "server error", hl = "ErrorMsg" }
    end
    if state == "restarting" or state == "starting" or state == "initializing" then
        return { icon = "🟡", label = state, hl = "WarningMsg" }
    end
    if state == "ready" then
        return { icon = "🟢", label = "live", hl = "DiagnosticOk" }
    end
    if state == "stopped" or state == "" then
        return { icon = "⏸", label = "no server", hl = "Comment" }
    end
    return { icon = "·", label = state, hl = "Comment" }
end

function M._set_assistant_badge(row)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then return end
    local live = _compute_liveness()
    local ext = vim.api.nvim_buf_set_extmark(M.buf, M.liveness_ns, row, 0, {
        virt_text = { { "  " .. live.icon .. " " .. live.label, live.hl } },
        virt_text_pos = "eol",
        hl_mode = "combine",
    })
    table.insert(M._assistant_header_lines, { row = row, id = ext })
end

local function _refresh_liveness()
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then return end
    local live = _compute_liveness()
    -- refresh top-of-buffer sticky line
    if M._top_line_extmark then
        pcall(vim.api.nvim_buf_del_extmark, M.buf, M.liveness_ns, M._top_line_extmark)
    end
    M._top_line_extmark = vim.api.nvim_buf_set_extmark(M.buf, M.liveness_ns, 0, 0, {
        virt_lines = { { { "poor-cli · " .. live.icon .. " " .. live.label, live.hl } } },
        virt_lines_above = true,
    })
    -- refresh each assistant header virt_text in place
    local kept = {}
    for _, entry in ipairs(M._assistant_header_lines) do
        local pos = vim.api.nvim_buf_get_extmark_by_id(M.buf, M.liveness_ns, entry.id, {})
        pcall(vim.api.nvim_buf_del_extmark, M.buf, M.liveness_ns, entry.id)
        if pos and pos[1] then
            local new_id = vim.api.nvim_buf_set_extmark(M.buf, M.liveness_ns, pos[1], 0, {
                virt_text = { { "  " .. live.icon .. " " .. live.label, live.hl } },
                virt_text_pos = "eol",
                hl_mode = "combine",
            })
            table.insert(kept, { row = pos[1], id = new_id })
        end
    end
    M._assistant_header_lines = kept
end

M._refresh_liveness = _refresh_liveness   -- test hook
M._compute_liveness = _compute_liveness   -- test hook

-- Tool-call rendering state. Inline running-indicator + truncated-result
-- expansion. _pending_tools is a FIFO of in-flight tool calls so _append_tool_result
-- can locate the matching "⠋ running…" line and replace it in place.
-- _tool_full_results maps extmark id → full text for <CR>-expand.
M.tool_ns = M.tool_ns or vim.api.nvim_create_namespace("poor-cli-tool")
M._pending_tools = M._pending_tools or {}
M._tool_full_results = M._tool_full_results or {}
M._tool_spinner_timer = M._tool_spinner_timer or nil
M._tool_spinner_tick = 0

local function _tool_spinner_frame()
    local frames = SPINNER_FRAMES or { "|", "/", "-", "\\" }
    return frames[(M._tool_spinner_tick % #frames) + 1]
end

local function _update_tool_spinners()
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then return end
    if #M._pending_tools == 0 then return end
    M._tool_spinner_tick = M._tool_spinner_tick + 1
    local frame = _tool_spinner_frame()
    for _, pending in ipairs(M._pending_tools) do
        local pos = vim.api.nvim_buf_get_extmark_by_id(M.buf, M.tool_ns, pending.extmark_id, {})
        if pos and pos[1] then
            local elapsed_s = math.max(0, math.floor(((vim.loop.hrtime() or 0) - (pending.started_ns or 0)) / 1e9))
            local line = string.format("%s running %s… (%ds)", frame, pending.name or "tool", elapsed_s)
            pcall(vim.api.nvim_buf_set_lines, M.buf, pos[1], pos[1] + 1, false, { line })
        end
    end
end

local function _ensure_tool_spinner_timer()
    if M._tool_spinner_timer or not vim.loop.new_timer then return end
    M._tool_spinner_timer = vim.loop.new_timer()
    M._tool_spinner_timer:start(120, 120, vim.schedule_wrap(function()
        if #M._pending_tools == 0 then
            if M._tool_spinner_timer then
                pcall(M._tool_spinner_timer.stop, M._tool_spinner_timer)
                pcall(M._tool_spinner_timer.close, M._tool_spinner_timer)
                M._tool_spinner_timer = nil
            end
            return
        end
        _update_tool_spinners()
    end))
end

function M._append_tool_call(name, args)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    local line_count = vim.api.nvim_buf_line_count(M.buf)
    local args_str = type(args) == "table" and vim.inspect(args) or tostring(args or "")
    local args_lines = vim.split(args_str, "\n", { plain = true })
    -- header + args fence + running line + blank; running line is the one
    -- we'll replace when the result arrives.
    local initial = string.format("%s running %s… (0s)", _tool_spinner_frame(), name or "tool")
    local block = { "**🔧 " .. (name or "tool") .. "**", "```" }
    for _, l in ipairs(args_lines) do table.insert(block, l) end
    table.insert(block, "```")
    table.insert(block, initial)
    table.insert(block, "")
    vim.api.nvim_buf_set_lines(M.buf, line_count, line_count, false, block)
    local running_line = line_count + (#block - 2) -- 0-indexed row of the "running..." line
    local extmark_id = vim.api.nvim_buf_set_extmark(M.buf, M.tool_ns, running_line, 0, {})
    table.insert(M._pending_tools, {
        name = name or "tool",
        extmark_id = extmark_id,
        started_ns = vim.loop.hrtime and vim.loop.hrtime() or 0,
    })
    _ensure_tool_spinner_timer()
end

local function _take_pending_tool(name)
    -- FIFO match by name; if the backend sends results out of order for
    -- parallel tool calls with the same name, first-pending wins.
    for i, p in ipairs(M._pending_tools) do
        if p.name == name then return table.remove(M._pending_tools, i) end
    end
    return M._pending_tools[1] and table.remove(M._pending_tools, 1) or nil
end

function M._append_tool_result(name, result, original_size, filtered_size)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    local full_str = tostring(result or "")
    local truncated = #full_str > 500
    local display_str = truncated and (full_str:sub(1, 500) .. "…") or full_str
    local size_note = ""
    if tonumber(original_size or 0) > 0 and tonumber(filtered_size or 0) > 0 and original_size ~= filtered_size then
        size_note = string.format(" (%.1f KB → %.1f KB)", original_size / 1024, filtered_size / 1024)
    end
    local header = "**✓ " .. (name or "tool") .. " result" .. size_note .. "**"

    local pending = _take_pending_tool(name or "tool")
    local elapsed_suffix = ""
    if pending and pending.started_ns and vim.loop.hrtime then
        local ms = math.floor((vim.loop.hrtime() - pending.started_ns) / 1000000)
        elapsed_suffix = string.format(" · %dms", ms)
    end
    local result_lines = { header .. elapsed_suffix, "```", display_str, "```", "" }

    if pending then
        local pos = vim.api.nvim_buf_get_extmark_by_id(M.buf, M.tool_ns, pending.extmark_id, {})
        pcall(vim.api.nvim_buf_del_extmark, M.buf, M.tool_ns, pending.extmark_id)
        if pos and pos[1] then
            -- replace the single "running…" line with the result block in place
            pcall(vim.api.nvim_buf_set_lines, M.buf, pos[1], pos[1] + 1, false, result_lines)
            if truncated then
                local full_ext = vim.api.nvim_buf_set_extmark(M.buf, M.tool_ns, pos[1], 0, {
                    virt_text = { { string.format(" [%d chars truncated · <CR> to expand]", #full_str - 500), "Comment" } },
                    virt_text_pos = "eol",
                    hl_mode = "combine",
                })
                M._tool_full_results[full_ext] = {
                    full = full_str,
                    header = header .. elapsed_suffix,
                    start_row = pos[1],
                    end_row = pos[1] + #result_lines,
                }
            end
            return
        end
    end
    -- fallback: no pending entry matched (e.g. result without start event) —
    -- append at end-of-buffer as before, but still mark truncation
    local line_count = vim.api.nvim_buf_line_count(M.buf)
    vim.api.nvim_buf_set_lines(M.buf, line_count, line_count, false, result_lines)
    if truncated then
        local full_ext = vim.api.nvim_buf_set_extmark(M.buf, M.tool_ns, line_count, 0, {
            virt_text = { { string.format(" [%d chars truncated · <CR> to expand]", #full_str - 500), "Comment" } },
            virt_text_pos = "eol",
            hl_mode = "combine",
        })
        M._tool_full_results[full_ext] = {
            full = full_str,
            header = header .. elapsed_suffix,
            start_row = line_count,
            end_row = line_count + #result_lines,
        }
    end
end

-- Look up a truncated-tool-result extmark at or above the cursor's row.
-- Returns { extmark_id, entry } or nil.
function M._tool_result_at_cursor()
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then return nil end
    local row = (vim.api.nvim_win_get_cursor(0) or { 1, 0 })[1] - 1
    local marks = vim.api.nvim_buf_get_extmarks(M.buf, M.tool_ns, 0, -1, { details = true })
    local best
    for _, m in ipairs(marks) do
        local id, mrow = m[1], m[2]
        local entry = M._tool_full_results[id]
        if entry and mrow <= row and row < entry.end_row then
            if not best or mrow > best.row then
                best = { id = id, row = mrow, entry = entry }
            end
        end
    end
    return best
end

function M.expand_tool_result_at_cursor()
    local hit = M._tool_result_at_cursor()
    if not hit then return false end
    local entry = hit.entry
    local new_lines = { entry.header .. " (expanded)", "```" }
    for _, line in ipairs(vim.split(entry.full, "\n", { plain = true })) do
        table.insert(new_lines, line)
    end
    table.insert(new_lines, "```")
    table.insert(new_lines, "")
    vim.bo[M.buf].modifiable = true
    pcall(vim.api.nvim_buf_set_lines, M.buf, entry.start_row, entry.end_row, false, new_lines)
    pcall(vim.api.nvim_buf_del_extmark, M.buf, M.tool_ns, hit.id)
    M._tool_full_results[hit.id] = nil
    return true
end

function M._append_tool_stream_chunk(name, chunk)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    local line_count = vim.api.nvim_buf_line_count(M.buf)
    local lines = vim.split(tostring(chunk or ""), "\n", { plain = true })
    if lines[#lines] == "" then
        table.remove(lines, #lines)
    end
    if #lines == 0 then
        return
    end
    local display = { "**" .. (name or "tool") .. " output**", "```" }
    for _, line in ipairs(lines) do
        table.insert(display, line)
    end
    table.insert(display, "```")
    table.insert(display, "")
    vim.api.nvim_buf_set_lines(M.buf, line_count, line_count, false, display)
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
    highlight_diff_block(M.buf, line_count, line_count + #lines)
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

    vim.keymap.set("n", "S", function()
        vim.cmd("PoorCLICollabQuick")
    end, { buffer = M.buf, desc = "Share collaboration invite", nowait = true, silent = true })

    vim.keymap.set("n", "<CR>", function()
        -- Context-sensitive: expand a truncated tool result if the cursor
        -- is on one, otherwise fall through to the send prompt.
        if M.expand_tool_result_at_cursor() then return end
        M.prompt_and_send()
    end, { buffer = M.buf, desc = "Send message (or expand tool result under cursor)", nowait = true, silent = true })
    vim.keymap.set("n", "<leader>rr", function()
        M.regenerate_turn()
    end, { buffer = M.buf, desc = "Regenerate assistant turn", nowait = true, silent = true })
    vim.keymap.set("n", "<leader>ee", function()
        M.edit_resend_turn()
    end, { buffer = M.buf, desc = "Edit and resend user turn", nowait = true, silent = true })
    vim.keymap.set("n", "<leader>ex", function()
        M.pick_export_format()
    end, { buffer = M.buf, desc = "Export conversation", nowait = true, silent = true })
    vim.keymap.set("n", "[[", function()
        M.switch_sibling("prev")
    end, { buffer = M.buf, desc = "Previous branch sibling", nowait = true, silent = true })
    vim.keymap.set("n", "]]", function()
        M.switch_sibling("next")
    end, { buffer = M.buf, desc = "Next branch sibling", nowait = true, silent = true })
    vim.keymap.set("n", "yc", function()
        M.yank_codeblock()
    end, { buffer = M.buf, desc = "Yank code block", nowait = true, silent = true })
    vim.keymap.set("n", "<leader>ya", function()
        M.apply_codeblock()
    end, { buffer = M.buf, desc = "Apply code block", nowait = true, silent = true })
    vim.keymap.set("n", "<leader>yl", function()
        M.open_codeblock_scratch()
    end, { buffer = M.buf, desc = "Open code block scratch", nowait = true, silent = true })
    local ok_dap, dap_bridge = pcall(require, "poor-cli.integrations.dap")
    if ok_dap and type(dap_bridge.attach) == "function" then
        dap_bridge.attach(M.buf)
    end

    -- re-apply on BufEnter in case a filetype plugin (e.g. vim-markdown) clobbers <CR>
    vim.api.nvim_create_autocmd("BufEnter", {
        buffer = M.buf,
        callback = function()
            vim.keymap.set("n", "<CR>", function()
                M.prompt_and_send()
            end, { buffer = M.buf, desc = "Send message", nowait = true, silent = true })
            vim.keymap.set("n", "S", function()
                vim.cmd("PoorCLICollabQuick")
            end, { buffer = M.buf, desc = "Share collaboration invite", nowait = true, silent = true })
            vim.keymap.set("n", "<leader>rr", function()
                M.regenerate_turn()
            end, { buffer = M.buf, desc = "Regenerate assistant turn", nowait = true, silent = true })
            vim.keymap.set("n", "<leader>ee", function()
                M.edit_resend_turn()
            end, { buffer = M.buf, desc = "Edit and resend user turn", nowait = true, silent = true })
            vim.keymap.set("n", "<leader>ex", function()
                M.pick_export_format()
            end, { buffer = M.buf, desc = "Export conversation", nowait = true, silent = true })
            vim.keymap.set("n", "[[", function()
                M.switch_sibling("prev")
            end, { buffer = M.buf, desc = "Previous branch sibling", nowait = true, silent = true })
            vim.keymap.set("n", "]]", function()
                M.switch_sibling("next")
            end, { buffer = M.buf, desc = "Next branch sibling", nowait = true, silent = true })
            vim.keymap.set("n", "yc", function()
                M.yank_codeblock()
            end, { buffer = M.buf, desc = "Yank code block", nowait = true, silent = true })
            vim.keymap.set("n", "<leader>ya", function()
                M.apply_codeblock()
            end, { buffer = M.buf, desc = "Apply code block", nowait = true, silent = true })
            vim.keymap.set("n", "<leader>yl", function()
                M.open_codeblock_scratch()
            end, { buffer = M.buf, desc = "Open code block scratch", nowait = true, silent = true })
            local ok_buf_dap, buf_dap_bridge = pcall(require, "poor-cli.integrations.dap")
            if ok_buf_dap and type(buf_dap_bridge.attach) == "function" then
                buf_dap_bridge.attach(M.buf)
            end
        end,
    })
end

-- ─────────────────── Chat Input with @/slash completion ───────────────────

local function parse_audit_export_args(raw)
    local args = vim.split(raw or "", "%s+", { trimempty = true })
    local params = {}
    local idx = 1
    while idx <= #args do
        local item = args[idx]
        if item == "/audit-export" then
            idx = idx + 1
        elseif item == "--since" or item == "--from" then
            params.since = args[idx + 1]
            idx = idx + 2
        elseif item == "--until" then
            params["until"] = args[idx + 1]
            idx = idx + 2
        elseif item == "--to" or item == "--out" or item == "--output" then
            params.outputPath = args[idx + 1]
            idx = idx + 2
        else
            idx = idx + 1
        end
    end
    return params
end

-- map slash commands to their PoorCLI handlers
local SLASH_HANDLERS = {
    ["/clear"]    = function() M.clear() end,
    ["/cancel"]   = function() M.cancel_active_stream("Cancelled by user.") end,
    ["/queue"]    = function() M.open_queue_manager() end,
    ["/resume"]   = function() vim.cmd("PoorCLISessionRestore") end,
    ["/sessions"] = function() vim.cmd("PoorCLISessions") end,
    ["/save"]     = function() vim.cmd("PoorCLISessionSave") end,
    ["/status"]   = function() vim.cmd("PoorCLIStatus") end,
    ["/switch"]   = function() vim.cmd("PoorCLISwitchProvider") end,
    ["/explain"]  = function() vim.cmd("PoorCLIExplain") end,
    ["/refactor"] = function() vim.cmd("PoorCLIRefactor") end,
    ["/test"]     = function() vim.cmd("PoorCLITest") end,
    ["/doc"]      = function() vim.cmd("PoorCLIDoc") end,
    ["/commit"]   = function() vim.cmd("PoorCLICommit") end,
    ["/fix"]      = function() vim.cmd("PoorCLIFixDiagnostics") end,
    ["/context"]  = function() vim.cmd("PoorCLIContext") end,
    ["/rules"]    = function() vim.cmd("PoorCLIRules") end,
    ["/cost"]     = function() vim.cmd("PoorCLICost") end,
    ["/audit-export"] = function(line)
        rpc.request("audit/exportRange", parse_audit_export_args(line), function(result, err)
            vim.schedule(function()
                if err then
                    require("poor-cli.notify").notify("[poor-cli] Audit export failed: " .. rpc.format_error(err), vim.log.levels.ERROR)
                    return
                end
                if type(result) == "table" and result.path then
                    require("poor-cli.notify").notify("[poor-cli] Exported " .. tostring(result.count or 0) .. " audit events to " .. tostring(result.path), vim.log.levels.INFO)
                else
                    require("poor-cli.notify").notify("[poor-cli] Audit export returned " .. tostring(type(result) == "table" and result.count or 0) .. " events", vim.log.levels.INFO)
                end
            end)
        end)
    end,
    ["/doctor"]   = function() vim.cmd("PoorCLIDoctor") end,
    ["/help"]     = function() vim.cmd("PoorCLIHelp") end,
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
    elseif before:match("^/[%w%-]*$") then
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

local function slash_command_name(raw)
    if type(raw) ~= "table" then return "" end
    return tostring(raw.name or raw.command or raw.id or ""):match("^%s*(.-)%s*$")
end

local function slash_command_description(raw)
    if type(raw) ~= "table" then return "" end
    return (tostring(raw.description or raw.summary or raw.desc or ""):gsub("\n.*$", ""))
end

local function slash_command_takes_args(raw)
    if type(raw) ~= "table" then return false end
    if raw.takesArgs ~= nil then return raw.takesArgs == true end
    if raw.takes_args ~= nil then return raw.takes_args == true end
    if type(raw.args) == "table" and #raw.args > 0 then return true end
    local name = slash_command_name(raw)
    local usage = tostring(raw.usage or "")
    return usage:sub(1, #name) == name and usage:sub(#name + 1):match("%S") ~= nil
end

local function slash_command_preview(raw)
    local lines = { slash_command_name(raw) }
    local description = slash_command_description(raw)
    if description ~= "" then vim.list_extend(lines, { "", description }) end
    if type(raw) == "table" and raw.usage and raw.usage ~= "" then vim.list_extend(lines, { "", "Usage: " .. tostring(raw.usage) }) end
    if type(raw) == "table" and type(raw.examples) == "table" and #raw.examples > 0 then
        vim.list_extend(lines, { "", "Examples:" })
        for _, example in ipairs(raw.examples) do table.insert(lines, tostring(example)) end
    end
    return table.concat(lines, "\n")
end

local function slash_picker_items(result)
    local commands = type(result) == "table" and (result.commands or result.items or result) or {}
    local items = {}
    for _, raw in ipairs(commands) do
        local name = slash_command_name(raw)
        if name:sub(1, 1) == "/" then
            local desc = slash_command_description(raw)
            table.insert(items, {
                id = name,
                label = desc ~= "" and (name .. "  " .. desc) or name,
                preview = slash_command_preview(raw),
                data = raw,
            })
        end
    end
    return items
end

local function slash_at_fresh_input(buf, win)
    if not buf or not vim.api.nvim_buf_is_valid(buf) or not win or not vim.api.nvim_win_is_valid(win) then return false end
    local cursor = vim.api.nvim_win_get_cursor(win)
    return cursor[2] == 0 and (vim.api.nvim_buf_get_lines(buf, cursor[1] - 1, cursor[1], false)[1] or "") == ""
end

local function input_has_bare_slash(buf, win)
    if not buf or not vim.api.nvim_buf_is_valid(buf) or not win or not vim.api.nvim_win_is_valid(win) then return false end
    local cursor = vim.api.nvim_win_get_cursor(win)
    return (vim.api.nvim_buf_get_lines(buf, cursor[1] - 1, cursor[1], false)[1] or "") == "/"
end

local function insert_slash_command(raw, buf, win)
    local name = slash_command_name(raw)
    if name == "" or not buf or not vim.api.nvim_buf_is_valid(buf) or not win or not vim.api.nvim_win_is_valid(win) then return false end
    local row = vim.api.nvim_win_get_cursor(win)[1]
    local line = vim.api.nvim_buf_get_lines(buf, row - 1, row, false)[1] or ""
    local _, finish = line:find("^/[%w%-]*")
    if not finish then return false end
    local suffix = line:sub(finish + 1)
    local wants_space = slash_command_takes_args(raw)
    local spacer = wants_space and not suffix:match("^%s") and " " or ""
    vim.api.nvim_buf_set_lines(buf, row - 1, row, false, { name .. spacer .. suffix })
    pcall(vim.api.nvim_win_set_cursor, win, { row, #name + (wants_space and 1 or 0) })
    if suffix == "" then
        pcall(vim.api.nvim_set_current_win, win)
        pcall(vim.cmd, "startinsert!")
    end
    return true
end

local function open_slash_picker(buf, win)
    rpc.request("commands.list", {}, function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] slash commands failed: " .. rpc.format_error(err), vim.log.levels.WARN)
                return
            end
            if not input_has_bare_slash(buf, win) then return end
            local items = slash_picker_items(result)
            if #items == 0 then return end
            pickers.pick(items, {
                title = "Slash Commands",
                on_pick = function(command)
                    insert_slash_command(command, buf, win)
                end,
            })
        end)
    end)
end

local function trigger_slash_picker(buf, win, char)
    if char ~= "/" or not slash_at_fresh_input(buf, win) then return false end
    vim.schedule(function()
        if input_has_bare_slash(buf, win) then open_slash_picker(buf, win) end
    end)
    return true
end

local function mention_target_buf()
    local win = M.last_non_chat_win
    if win and vim.api.nvim_win_is_valid(win) then
        local buf = vim.api.nvim_win_get_buf(win)
        if is_target_buf(buf) then return buf end
    end
    local current = vim.api.nvim_get_current_buf()
    if is_target_buf(current) then return current end
    return nil
end

local function mention_at_word_start(buf, win)
    if not buf or not vim.api.nvim_buf_is_valid(buf) or not win or not vim.api.nvim_win_is_valid(win) then return false end
    local cursor = vim.api.nvim_win_get_cursor(win)
    local line = vim.api.nvim_buf_get_lines(buf, cursor[1] - 1, cursor[1], false)[1] or ""
    local before = line:sub(1, cursor[2])
    return before == "" or before:sub(-1):match("%s") ~= nil
end

local function source_trigger_at_cursor(buf, win)
    if not buf or not vim.api.nvim_buf_is_valid(buf) or not win or not vim.api.nvim_win_is_valid(win) then return nil end
    local cursor = vim.api.nvim_win_get_cursor(win)
    local line = vim.api.nvim_buf_get_lines(buf, cursor[1] - 1, cursor[1], false)[1] or ""
    for _, before in ipairs({ line:sub(1, cursor[2] + 1), line:sub(1, cursor[2]) }) do
        local at_pos, _, source = before:find("@([%w_%-]+):$")
        if at_pos and (at_pos == 1 or before:sub(at_pos - 1, at_pos - 1):match("%s") ~= nil) then
            return source:lower()
        end
    end
    return nil
end

local function source_prefix_at_cursor(buf, win)
    if not buf or not vim.api.nvim_buf_is_valid(buf) or not win or not vim.api.nvim_win_is_valid(win) then return nil end
    local cursor = vim.api.nvim_win_get_cursor(win)
    local line = vim.api.nvim_buf_get_lines(buf, cursor[1] - 1, cursor[1], false)[1] or ""
    for _, before in ipairs({ line:sub(1, cursor[2] + 1), line:sub(1, cursor[2]) }) do
        local at_pos, _, source = before:find("@([%w_%-]+)$")
        if at_pos and (at_pos == 1 or before:sub(at_pos - 1, at_pos - 1):match("%s") ~= nil) then
            return source:lower()
        end
    end
    return nil
end

local function insert_mention_token(token, buf, win, source)
    if not token or token == "" or not buf or not vim.api.nvim_buf_is_valid(buf) or not win or not vim.api.nvim_win_is_valid(win) then return false end
    local cursor = vim.api.nvim_win_get_cursor(win)
    local row, col = cursor[1], cursor[2]
    local line = vim.api.nvim_buf_get_lines(buf, row - 1, row, false)[1] or ""
    local before, after, prefix_start
    for _, end_col in ipairs({ col, col + 1 }) do
        local candidate_before = line:sub(1, end_col)
        local candidate_start
        if source and source ~= "" then
            local escaped = source:gsub("([^%w])", "%%%1")
            candidate_start = candidate_before:find("@" .. escaped .. ":$")
        end
        if not candidate_start then
            candidate_start = candidate_before:find("@$")
        end
        if candidate_start then
            before = candidate_before
            after = line:sub(end_col + 1)
            prefix_start = candidate_start
            break
        end
    end
    if not prefix_start then return false end
    local new_before = before:sub(1, prefix_start - 1) .. token
    local spacer = after:match("^%s") and "" or " "
    vim.api.nvim_buf_set_lines(buf, row - 1, row, false, { new_before .. spacer .. after })
    pcall(vim.api.nvim_win_set_cursor, win, { row, #new_before + #spacer })
    pcall(vim.api.nvim_set_current_win, win)
    pcall(vim.cmd, "startinsert!")
    return true
end

local function open_mention_item_picker(source, buf, win, replace_source)
    local opts = {
        target_buf = mention_target_buf(),
        input_buf = buf,
        input_win = win,
        insert_token = function(token)
            return insert_mention_token(token, buf, win, replace_source and source or nil)
        end,
    }
    if mentions.open_source(source, opts) then return true end
    local items = mentions.source_items(source, opts)
    if #items == 0 then
        require("poor-cli.notify").notify("[poor-cli] no @" .. source .. ": mentions", vim.log.levels.INFO)
        return false
    end
    pickers.pick(items, {
        title = "Mention @" .. source .. ":",
        on_pick = function(data)
            local token = type(data) == "table" and data.token or nil
            insert_mention_token(token, buf, win, replace_source and source or nil)
        end,
    })
    return true
end

local function open_mention_source_picker(buf, win)
    local items = mentions.source_picker_items()
    if #items == 0 then return false end
    pickers.pick(items, {
        title = "Mention Sources",
        on_pick = function(data)
            if type(data) == "table" and data.name then
                open_mention_item_picker(data.name, buf, win, false)
            end
        end,
    })
    return true
end

local function trigger_mention_picker(buf, win, char)
    if char == "@" then
        if not mention_at_word_start(buf, win) then return false end
        -- honor `mentions.default_source` so `@` can jump straight to
        -- a specific source (Claude-Code / Codex behavior) instead of
        -- the multi-source picker.
        local mentions_cfg = config.get("mentions") or {}
        local default_source = tostring(mentions_cfg.default_source or "file"):lower()
        vim.schedule(function()
            if default_source == "picker" then
                open_mention_source_picker(buf, win)
            elseif default_source == "file" or default_source == "buffer" or default_source == "lsp" then
                if not open_mention_item_picker(default_source, buf, win, false) then
                    -- fallback: if the preferred source has no items, let the
                    -- user see the multi-source picker instead of a dead end.
                    open_mention_source_picker(buf, win)
                end
            else
                open_mention_source_picker(buf, win)
            end
        end)
        return true
    end
    if char ~= ":" then return false end
    local pending_source = source_prefix_at_cursor(buf, win)
    vim.schedule(function()
        local source = pending_source or source_trigger_at_cursor(buf, win)
        if source then open_mention_item_picker(source, buf, win, true) end
    end)
    return pending_source ~= nil
end

M._test_slash_picker_items = slash_picker_items
M._test_insert_slash_command = insert_slash_command
M._test_trigger_slash_picker = trigger_slash_picker
M._test_trigger_mention_picker = trigger_mention_picker
M._test_insert_mention_token = insert_mention_token
M._test_mention_source_items = mentions.source_items
M._test_mention_source_picker_items = mentions.source_picker_items

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

function M.prompt_and_send(opts)
    if type(opts) == "string" then opts = { initial_text = opts } end
    opts = opts or {}
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
    if opts.initial_text and opts.initial_text ~= "" then
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, vim.split(opts.initial_text, "\n", { plain = true }))
        local first_line = vim.api.nvim_buf_get_lines(buf, 0, 1, false)[1] or ""
        pcall(vim.api.nvim_win_set_cursor, ip.win, { 1, #first_line })
    end

    -- submit
    vim.keymap.set("i", "<CR>", function()
        local line = table.concat(vim.api.nvim_buf_get_lines(buf, 0, -1, false), "\n")
        local edit_state = opts.edit_state
        clear_local_typing()
        input_close()
        vim.cmd("stopinsert")
        if line == "" then
            if edit_state then clear_edit_state() end
            return
        end

        if edit_state then
            trim_for_edit(edit_state)
            clear_edit_state()
            M.send(line, { edit_turn_id = edit_state.turn_id })
            return
        end

        -- check for slash command
        local cmd = line:match("^(/[%w%-]+)")
        if cmd and SLASH_HANDLERS[cmd] then
            SLASH_HANDLERS[cmd](line)
            return
        end

        M.send(line)
    end, { buffer = buf, nowait = true })

    -- cancel
    vim.keymap.set("i", "<Esc>", function()
        clear_local_typing()
        input_close()
        if opts.edit_state then clear_edit_state() end
        vim.cmd("stopinsert")
    end, { buffer = buf, nowait = true })

    vim.keymap.set("n", "<Esc>", function()
        clear_local_typing()
        input_close()
        if opts.edit_state then clear_edit_state() end
    end, { buffer = buf, nowait = true })

    vim.keymap.set("n", "q", function()
        clear_local_typing()
        input_close()
        if opts.edit_state then clear_edit_state() end
    end, { buffer = buf, nowait = true })

    -- Tab to accept completion, Shift-Tab or Ctrl-p to navigate
    vim.keymap.set("i", "<Tab>", function()
        if not accept_completion() then
            vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes("<Tab>", true, false, true), "n", false)
        end
    end, { buffer = buf, nowait = true })

    vim.keymap.set("i", "<C-n>", function() menu_select_next() end, { buffer = buf, nowait = true })
    vim.keymap.set("i", "<C-p>", function() menu_select_prev() end, { buffer = buf, nowait = true })

    vim.api.nvim_create_autocmd("InsertCharPre", {
        buffer = buf,
        callback = function()
            trigger_slash_picker(buf, ip.win, vim.v.char)
            trigger_mention_picker(buf, ip.win, vim.v.char)
        end,
    })

    -- live update completions on text change
    vim.api.nvim_create_autocmd({ "TextChangedI", "TextChanged" }, {
        buffer = buf,
        callback = function()
            mark_local_typing()
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
        require("poor-cli.notify").notify("[poor-cli] Select text first", vim.log.levels.WARN)
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
            "Use `:PoorCLISend` or press `<CR>` at the bottom to send a message.",
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
        require("poor-cli.notify").notify("[poor-cli] Queue is empty", vim.log.levels.INFO)
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
            require("poor-cli.notify").notify("[poor-cli] Queue cleared", vim.log.levels.INFO)
        end
    end, { buffer = buf, nowait = true })

    vim.keymap.set("n", "x", function()
        local idx = queue_mgr_cursor_index()
        if not idx then return end
        table.remove(M.message_queue, idx)
        queue_mgr_render()
        if #M.message_queue == 0 then
            queue_mgr_close()
            require("poor-cli.notify").notify("[poor-cli] Queue cleared", vim.log.levels.INFO)
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
        require("poor-cli.notify").notify("[poor-cli] Queue cleared", vim.log.levels.INFO)
    end, { buffer = buf, nowait = true })
end

return M
