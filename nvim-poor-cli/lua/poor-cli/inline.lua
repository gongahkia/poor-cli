-- poor-cli/inline.lua
-- Inline ghost text completion (like Windsurf/Copilot)

local config = require("poor-cli.config")
local rpc = require("poor-cli.rpc")

local M = {}

M.ns_id = vim.api.nvim_create_namespace("poor-cli-inline")
M.current_completion = nil
M.inline_request_token = 0
M.pending_inline_request = nil -- { token, request_id, rpc_request_id, bufnr, line, col, changedtick, partial_text }
M.status = {
    state = "idle",
    reason = "",
    request_id = "",
}
M._auto_trigger_timer = nil
M.cycle_state = nil
M.last_cycled_index = 1

local cancel_pending_inline_request
local SKIP_NODES = {
    default = { "comment", "line_comment", "block_comment", "string", "string_content" },
    javascript = { "comment", "string", "string_fragment", "template_string" },
    javascriptreact = { "comment", "string", "string_fragment", "template_string" },
    lua = { "comment", "string", "string_content" },
    python = { "comment", "string", "string_content" },
    rust = { "line_comment", "block_comment", "string_literal", "raw_string_literal" },
    typescript = { "comment", "string", "string_fragment", "template_string" },
    typescriptreact = { "comment", "string", "string_fragment", "template_string" },
}

local function emit_status_changed()
    vim.api.nvim_exec_autocmds("User", {
        pattern = "PoorCLIInlineStatusChanged",
        data = M.get_status(),
    })
end

local function set_status(state, reason, request_id)
    M.status = {
        state = state,
        reason = reason or "",
        request_id = request_id or "",
    }
    emit_status_changed()
end

local function byte_len(text)
    return vim.fn.strlen(text or "")
end

local function split_line_at_byte_col(line_text, byte_col)
    local max_col = byte_len(line_text)
    local safe_col = math.max(0, math.min(byte_col, max_col))
    local before = line_text:sub(1, safe_col)
    local after = line_text:sub(safe_col + 1)
    return before, after, safe_col
end

local function trim_head(text, max_chars)
    if max_chars <= 0 or byte_len(text) <= max_chars then
        return text
    end
    return text:sub(byte_len(text) - max_chars + 1)
end

local function trim_tail(text, max_chars)
    if max_chars <= 0 or byte_len(text) <= max_chars then
        return text
    end
    return text:sub(1, max_chars)
end

local function contains(list, item)
    if type(list) ~= "table" then
        return false
    end
    for _, value in ipairs(list) do
        if value == item then
            return true
        end
    end
    return false
end

local function current_prefix_length(bufnr, line, col)
    local current_line = vim.api.nvim_buf_get_lines(bufnr, line - 1, line, false)[1] or ""
    local prefix = current_line:sub(1, col)
    local token = prefix:match("([%w_]+)$") or ""
    return byte_len(token)
end

local function make_request_id()
    return string.format("inline-%d-%d", os.time(), M.inline_request_token + 1)
end

local function emit_completion_accepted(kind)
    vim.api.nvim_exec_autocmds("User", {
        pattern = "PoorCLICompletionAccepted",
        data = { kind = kind },
    })
end

local function completion_lines(text)
    return vim.split(text or "", "\n", { plain = true })
end

local function candidate_count()
    local count = tonumber(config.get("completion_candidates")) or 3
    return math.max(1, math.floor(count))
end

local function normalize_candidates(candidates)
    local normalized = {}
    if type(candidates) ~= "table" then
        return normalized
    end
    for _, candidate in ipairs(candidates) do
        if type(candidate) == "string" and candidate ~= "" then
            table.insert(normalized, candidate)
        end
    end
    return normalized
end

local function cursor_matches_cycle_state()
    local state = M.cycle_state
    if not state or not vim.api.nvim_buf_is_valid(state.bufnr) then
        return false
    end
    if vim.api.nvim_get_current_buf() ~= state.bufnr then
        return false
    end
    local cursor = vim.api.nvim_win_get_cursor(0)
    if cursor[1] ~= state.line or cursor[2] ~= state.col then
        return false
    end
    return vim.api.nvim_buf_get_changedtick(state.bufnr) == state.changedtick
end

local function invalidate_cycle_state()
    M.cycle_state = nil
    M.last_cycled_index = 1
end

local function set_cycle_state(candidates, index, bufnr, line, col)
    candidates = normalize_candidates(candidates)
    if #candidates < 2 then
        invalidate_cycle_state()
        return
    end
    index = math.max(1, math.min(tonumber(index) or 1, #candidates))
    M.cycle_state = {
        candidates = candidates,
        index = index,
        bufnr = bufnr,
        line = line,
        col = col,
        changedtick = vim.api.nvim_buf_get_changedtick(bufnr),
    }
    M.last_cycled_index = index
end

local function node_type(node)
    if not node then
        return nil
    end
    local kind = node.type
    if type(kind) == "function" then
        local ok, value = pcall(kind, node)
        if ok then return value end
    elseif type(kind) == "string" then
        return kind
    end
    return nil
end

local function parent_node(node)
    if not node then
        return nil
    end
    local parent = node.parent
    if type(parent) == "function" then
        local ok, value = pcall(parent, node)
        if ok then return value end
    end
    return nil
end

function M.is_syntax_region_blocked(bufnr)
    bufnr = bufnr or vim.api.nvim_get_current_buf()
    if not vim.treesitter or not vim.treesitter.get_node then
        return false
    end
    local ok, node = pcall(vim.treesitter.get_node, { bufnr = bufnr })
    if not ok then
        ok, node = pcall(vim.treesitter.get_node)
    end
    if not ok or not node then
        return false
    end
    local ft = vim.bo[bufnr].filetype or ""
    local skipped = SKIP_NODES[ft] or SKIP_NODES.default
    for _ = 1, 8 do
        local kind = node_type(node)
        if contains(skipped, kind) or contains(SKIP_NODES.default, kind) then
            return true
        end
        node = parent_node(node)
        if not node then
            return false
        end
    end
    return false
end

local function create_inline_request_context(bufnr, line, col)
    cancel_pending_inline_request()

    M.inline_request_token = M.inline_request_token + 1
    local context = {
        token = M.inline_request_token,
        request_id = make_request_id(),
        bufnr = bufnr,
        line = line,
        col = col,
        changedtick = vim.api.nvim_buf_get_changedtick(bufnr),
        partial_text = "",
    }
    M.pending_inline_request = context
    set_status("requesting", "", context.request_id)
    return context
end

local function is_request_active(context)
    return M.pending_inline_request and M.pending_inline_request.token == context.token
end

local function clear_request_if_active(context)
    if is_request_active(context) then
        M.pending_inline_request = nil
        if not M.current_completion then
            set_status("idle", "", "")
        end
    end
end

local function is_request_stale(context)
    if not vim.api.nvim_buf_is_valid(context.bufnr) then
        return true
    end

    if vim.api.nvim_get_current_buf() ~= context.bufnr then
        return true
    end

    local cursor = vim.api.nvim_win_get_cursor(0)
    if cursor[1] ~= context.line or cursor[2] ~= context.col then
        return true
    end

    local changedtick = vim.api.nvim_buf_get_changedtick(context.bufnr)
    return changedtick ~= context.changedtick
end

cancel_pending_inline_request = function()
    local context = M.pending_inline_request
    if not context then
        return
    end

    if context.rpc_request_id then
        rpc.cancel_request(context.rpc_request_id, {
            code = -32800,
            message = "Request cancelled",
            data = {
                request_id = context.request_id,
            },
        })
    end

    M.pending_inline_request = nil
    set_status("idle", "cancelled", "")
end

local function cancel_if_request_stale()
    local context = M.pending_inline_request
    if context and is_request_stale(context) then
        cancel_pending_inline_request()
    end
end

function M.get_status()
    return vim.deepcopy(M.status)
end

function M.is_enabled_for_buffer(bufnr, opts)
    bufnr = bufnr or vim.api.nvim_get_current_buf()
    opts = opts or {}

    if config.get("completion_enabled") == false then
        return false, "disabled"
    end

    local buftype = vim.bo[bufnr].buftype or ""
    if contains(config.get("completion_buftype_blocklist"), buftype) then
        return false, "blocked buftype: " .. buftype
    end

    local filetype = vim.bo[bufnr].filetype or ""
    local allowlist = config.get("completion_filetype_allowlist")
    if type(allowlist) == "table" and #allowlist > 0 and not contains(allowlist, filetype) then
        return false, "blocked filetype: " .. filetype
    end

    if contains(config.get("completion_filetype_blocklist"), filetype) then
        return false, "blocked filetype: " .. filetype
    end

    if not opts.manual and config.get("completion_manual_only") then
        return false, "manual only"
    end

    if not opts.manual and M.is_syntax_region_blocked(bufnr) then
        return false, "blocked syntax region"
    end

    local min_prefix = tonumber(config.get("completion_min_prefix")) or 0
    if not opts.manual and min_prefix > 0 then
        local cursor = vim.api.nvim_win_get_cursor(0)
        if current_prefix_length(bufnr, cursor[1], cursor[2]) < min_prefix then
            return false, "prefix too short"
        end
    end

    return true, ""
end

function M.show_ghost_text(text, opts)
    opts = opts or {}
    if not text or text == "" then
        return
    end

    local bufnr = vim.api.nvim_get_current_buf()
    local cursor = vim.api.nvim_win_get_cursor(0)
    local line = cursor[1] - 1
    local col = cursor[2]

    M.clear_ghost_text({ keep_preview = true, keep_cycle = opts.keep_cycle })

    local lines = vim.split(text, "\n", { plain = true })
    M.current_completion = {
        bufnr = bufnr,
        line = line,
        col = col,
        text = text,
    }
    if opts.candidates then
        set_cycle_state(opts.candidates, opts.index or 1, bufnr, cursor[1], col)
    end

    if #lines == 1 then
        vim.api.nvim_buf_set_extmark(bufnr, M.ns_id, line, col, {
            virt_text = { { lines[1], config.get("ghost_text_hl") } },
            virt_text_pos = "inline",
        })
    else
        vim.api.nvim_buf_set_extmark(bufnr, M.ns_id, line, col, {
            virt_text = { { lines[1], config.get("ghost_text_hl") } },
            virt_text_pos = "inline",
            virt_lines = vim.tbl_map(function(chunk)
                return { { chunk, config.get("ghost_text_hl") } }
            end, vim.list_slice(lines, 2)),
        })
    end

    local request_id = M.pending_inline_request and M.pending_inline_request.request_id or ""
    set_status("suggesting", "", request_id)
end

function M.clear_ghost_text(opts)
    opts = opts or {}
    local comp = M.current_completion
    local bufnr = comp and comp.bufnr or vim.api.nvim_get_current_buf()
    if vim.api.nvim_buf_is_valid(bufnr) then
        vim.api.nvim_buf_clear_namespace(bufnr, M.ns_id, 0, -1)
    end
    M.current_completion = nil
    if not opts.keep_cycle then
        invalidate_cycle_state()
    end
end

function M.accept()
    if not M.current_completion then
        return false
    end

    local comp = M.current_completion
    local bufnr = comp.bufnr
    local line = comp.line
    local col = comp.col
    local text = comp.text

    M.clear_ghost_text()

    local lines = vim.split(text, "\n", { plain = true })
    if #lines == 1 then
        local current_line = vim.api.nvim_buf_get_lines(bufnr, line, line + 1, false)[1] or ""
        local before, after, safe_col = split_line_at_byte_col(current_line, col)
        vim.api.nvim_buf_set_lines(bufnr, line, line + 1, false, { before .. text .. after })
        vim.api.nvim_win_set_cursor(0, { line + 1, safe_col + byte_len(text) })
    else
        local current_line = vim.api.nvim_buf_get_lines(bufnr, line, line + 1, false)[1] or ""
        local before, after = split_line_at_byte_col(current_line, col)
        lines[1] = before .. lines[1]
        lines[#lines] = lines[#lines] .. after
        vim.api.nvim_buf_set_lines(bufnr, line, line + 1, false, lines)
        local last_line = line + #lines
        local last_col = byte_len(lines[#lines]) - byte_len(after)
        vim.api.nvim_win_set_cursor(0, { last_line, last_col })
    end

    set_status("accepted", "", "")
    emit_completion_accepted("full")
    return true
end

function M.dismiss()
    M.clear_ghost_text()
    set_status("idle", "dismissed", "")
end

function M.build_completion_request(opts)
    local bufnr = opts.bufnr or vim.api.nvim_get_current_buf()
    local line = opts.line
    local col = opts.col
    local instruction = opts.instruction or ""
    local request_id = opts.request_id or ""
    local lines = vim.api.nvim_buf_get_lines(bufnr, 0, -1, false)
    local total_lines = #lines

    local max_lines_before = tonumber(config.get("completion_max_lines_before")) or 80
    local max_lines_after = tonumber(config.get("completion_max_lines_after")) or 80
    local start_line = math.max(1, line - max_lines_before)
    local end_line = math.min(total_lines, line + max_lines_after)

    local code_before = table.concat(vim.list_slice(lines, start_line, line - 1), "\n")
    if line <= total_lines then
        local current_line = lines[line] or ""
        local current_prefix = current_line:sub(1, col)
        if code_before ~= "" then
            code_before = code_before .. "\n" .. current_prefix
        else
            code_before = current_prefix
        end
    end

    local code_after = ""
    if line <= total_lines then
        local current_line = lines[line] or ""
        code_after = current_line:sub(col + 1)
    end
    if line < end_line then
        code_after = code_after .. "\n" .. table.concat(vim.list_slice(lines, line + 1, end_line), "\n")
    end

    local max_chars = tonumber(config.get("completion_max_chars")) or 16000
    local before_budget = math.floor(max_chars * 0.6)
    local after_budget = max_chars - before_budget
    code_before = trim_head(code_before, before_budget)
    code_after = trim_tail(code_after, after_budget)

    local lsp_context = ""
    local ok, lsp = pcall(require, "poor-cli.lsp")
    if ok then
        lsp_context = lsp.get_full_lsp_context() or ""
        local lsp_budget = tonumber(config.get("completion_lsp_context_max_chars")) or 4000
        lsp_context = trim_head(lsp_context, lsp_budget)
    end

    return {
        codeBefore = code_before,
        codeAfter = code_after,
        instruction = instruction,
        filePath = vim.fn.expand("%:p"),
        language = vim.bo[bufnr].filetype,
        lspContext = lsp_context,
        requestId = request_id,
        streamPartial = config.get("completion_stream_partial") == true,
        completions_count = opts.completions_count,
        n = opts.completions_count,
        provider = config.get("completion_provider"),
        model = config.get("completion_model"),
    }
end

local function handle_inline_response(context, result, err)
    if not is_request_active(context) then
        return
    end

    if err then
        clear_request_if_active(context)
        if err.code ~= -32800 then
            set_status("error", err.message or rpc.format_error(err), context.request_id)
            require("poor-cli.notify").notify("[poor-cli] Completion error: " .. rpc.format_error(err), vim.log.levels.ERROR)
        end
        return
    end

    if not result or not result.completion then
        clear_request_if_active(context)
        return
    end

    vim.schedule(function()
        if not is_request_active(context) then
            return
        end

        if is_request_stale(context) then
            clear_request_if_active(context)
            return
        end

        local candidates = normalize_candidates(result.completions or { result.completion })
        clear_request_if_active(context)
        M.show_ghost_text(result.completion, { candidates = candidates, index = 1 })
    end)
end

function M.cycle(delta)
    local state = M.cycle_state
    if not state or #state.candidates < 2 then
        return false
    end
    if not cursor_matches_cycle_state() then
        invalidate_cycle_state()
        return false
    end
    local next_index = ((state.index - 1 + delta) % #state.candidates) + 1
    state.index = next_index
    M.last_cycled_index = next_index
    M.show_ghost_text(state.candidates[next_index], { keep_cycle = true })
    return true
end

function M.cycle_next()
    return M.cycle(1)
end

function M.cycle_prev()
    return M.cycle(-1)
end

function M.cancel_active_request()
    local had_request = M.pending_inline_request ~= nil
    cancel_pending_inline_request()
    M.clear_ghost_text()
    return had_request
end

function M.trigger(opts)
    opts = opts or {}
    local manual = opts.manual ~= false

    if not rpc.is_running() then
        set_status("error", "server not running", "")
        require("poor-cli.notify").notify("[poor-cli] Server not running", vim.log.levels.WARN)
        return
    end

    -- short-circuit if the backend told us at init the API key is invalid:
    -- silently mark disabled for auto triggers so we don't hammer 401s on
    -- every keystroke; for manual triggers, surface the fix commands.
    local caps = (type(rpc.get_capabilities) == "function" and rpc.get_capabilities()) or rpc.capabilities or {}
    local validity = caps.apiKeyValidity or {}
    if validity.status == "invalid" then
        local provider = tostring(validity.provider or "?")
        set_status("disabled", "api key invalid: " .. provider, "")
        if manual then
            require("poor-cli.notify").notify(
                string.format(
                    "Blocked: API key for %s is invalid.\nFix with :PoorCLIConfig api-key or :PoorCLIHelp onboarding.",
                    provider
                ),
                vim.log.levels.ERROR,
                { title = "poor-cli", timeout = 8000 }
            )
        end
        return
    end

    local bufnr = vim.api.nvim_get_current_buf()
    local enabled, reason = M.is_enabled_for_buffer(bufnr, { manual = manual })
    if not enabled then
        set_status("disabled", reason, "")
        if manual then
            require("poor-cli.notify").notify("[poor-cli] Completion unavailable: " .. reason, vim.log.levels.WARN)
        end
        return
    end

    M.clear_ghost_text()

    local cursor = vim.api.nvim_win_get_cursor(0)
    local line = cursor[1]
    local col = cursor[2]
    local request_context = create_inline_request_context(bufnr, line, col)
    local payload = M.build_completion_request({
        bufnr = bufnr,
        line = line,
        col = col,
        instruction = opts.instruction or "",
        request_id = request_context.request_id,
        completions_count = opts.completions_count or candidate_count(),
    })
    if payload.completions_count > 1 then
        payload.streamPartial = false
    end

    -- show subtle "fetching..." hint while waiting
    local hint_ns = vim.api.nvim_create_namespace("poor-cli_fetch_hint")
    pcall(vim.api.nvim_buf_set_extmark, bufnr, hint_ns, line - 1, col, {
        virt_text = {{ " ...", "Comment" }}, virt_text_pos = "inline",
    })
    local request_id = rpc.request("poor-cli/inlineComplete", payload, function(result, err)
        pcall(vim.api.nvim_buf_clear_namespace, bufnr, hint_ns, 0, -1) -- clear hint
        handle_inline_response(request_context, result, err)
    end)

    request_context.rpc_request_id = request_id
    if not request_id then
        pcall(vim.api.nvim_buf_clear_namespace, bufnr, hint_ns, 0, -1)
        clear_request_if_active(request_context)
    end
end

function M.trigger_with_instruction(instruction)
    if not instruction then
        vim.ui.input({ prompt = "Instruction: " }, function(input)
            if input and input ~= "" then
                M.trigger_with_instruction(input)
            end
        end)
        return
    end

    M.trigger({
        manual = true,
        instruction = instruction,
    })
end

function M.complete_selection()
    local mode = vim.fn.mode()
    if mode ~= "v" and mode ~= "V" then
        require("poor-cli.notify").notify("[poor-cli] Select text first", vim.log.levels.WARN)
        return
    end

    local start_pos = vim.fn.getpos("'<")
    local end_pos = vim.fn.getpos("'>")
    local lines = vim.fn.getline(start_pos[2], end_pos[2])
    if type(lines) == "string" then
        lines = { lines }
    end

    local selected_text = table.concat(lines, "\n")

    vim.ui.input({ prompt = "Instruction: " }, function(instruction)
        if not instruction or instruction == "" then
            return
        end

        rpc.request("poor-cli/chat", {
            message = "Refactor/modify this code according to the instruction. "
                .. "Return ONLY the modified code, no explanations.\n\n"
                .. "Instruction: " .. instruction .. "\n\n"
                .. "Code:\n" .. selected_text,
        }, function(result, err)
            if err then
                require("poor-cli.notify").notify("[poor-cli] Error: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end

            if result and result.content then
                vim.schedule(function()
                    local new_lines = vim.split(result.content, "\n", { plain = true })
                    vim.api.nvim_buf_set_lines(0, start_pos[2] - 1, end_pos[2], false, new_lines)
                end)
            end
        end)
    end)
end

function M.accept_line()
    if not M.current_completion then
        return false
    end
    local comp = M.current_completion
    local text = comp.text
    local first_nl = text:find("\n")
    if not first_nl then
        return M.accept()
    end
    local line_text = text:sub(1, first_nl - 1)
    local remaining = text:sub(first_nl + 1)
    M.clear_ghost_text()
    local bufnr = comp.bufnr
    local line = comp.line
    local col = comp.col
    local current_line = vim.api.nvim_buf_get_lines(bufnr, line, line + 1, false)[1] or ""
    local before, after = split_line_at_byte_col(current_line, col)
    vim.api.nvim_buf_set_lines(bufnr, line, line + 1, false, { before .. line_text, after })
    vim.api.nvim_win_set_cursor(0, { line + 2, 0 })
    if remaining ~= "" then
        M.show_ghost_text(remaining)
    else
        set_status("accepted", "", "")
    end
    emit_completion_accepted("line")
    return true
end

function M.accept_word()
    if not M.current_completion then
        return false
    end
    local comp = M.current_completion
    local text = comp.text
    local word_end = text:match("^(%S+%s?)")
    if not word_end then
        return M.accept()
    end
    local remaining = text:sub(#word_end + 1)
    M.clear_ghost_text()
    local bufnr = comp.bufnr
    local line = comp.line
    local col = comp.col
    local current_line = vim.api.nvim_buf_get_lines(bufnr, line, line + 1, false)[1] or ""
    local before, after, safe_col = split_line_at_byte_col(current_line, col)
    if word_end:find("\n") then
        word_end = word_end:sub(1, word_end:find("\n") - 1)
        remaining = text:sub(#word_end + 1)
    end
    local new_line = before .. word_end .. after
    vim.api.nvim_buf_set_lines(bufnr, line, line + 1, false, { new_line })
    local new_col = safe_col + byte_len(word_end)
    vim.api.nvim_win_set_cursor(0, { line + 1, new_col })
    if remaining ~= "" then
        M.current_completion = { bufnr = bufnr, line = line, col = new_col, text = remaining }
        M.show_ghost_text(remaining)
    else
        set_status("accepted", "", "")
    end
    emit_completion_accepted("word")
    return true
end

function M.auto_trigger()
    local delay = config.get("trigger_delay") or 500
    if M._auto_trigger_timer then
        pcall(function()
            M._auto_trigger_timer:stop()
            M._auto_trigger_timer:close()
        end)
        M._auto_trigger_timer = nil
    end
    M._auto_trigger_timer = vim.defer_fn(function()
        M._auto_trigger_timer = nil
        if rpc.is_running() and not M.has_completion() then
            M.trigger({ manual = false })
        end
    end, delay)
end

function M.cancel_auto_trigger()
    if M._auto_trigger_timer then
        pcall(function()
            M._auto_trigger_timer:stop()
            M._auto_trigger_timer:close()
        end)
        M._auto_trigger_timer = nil
    end
end

function M.has_completion()
    return M.current_completion ~= nil
end

local request_cancel_group = vim.api.nvim_create_augroup("poor-cli-inline-request-cancel", { clear = true })
vim.api.nvim_create_autocmd({ "CursorMoved", "CursorMovedI", "TextChanged", "TextChangedI", "BufLeave" }, {
    group = request_cancel_group,
    callback = function()
        cancel_if_request_stale()
        if M.cycle_state and not cursor_matches_cycle_state() then
            invalidate_cycle_state()
        end
    end,
})

local inline_stream_group = vim.api.nvim_create_augroup("poor-cli-inline-stream", { clear = true })
vim.api.nvim_create_autocmd("User", {
    group = inline_stream_group,
    pattern = "PoorCLIInlineChunk",
    callback = function(ev)
        local data = ev.data or {}
        local context = M.pending_inline_request
        if not context or data.request_id ~= context.request_id then
            return
        end

        if data.done then
            return
        end

        context.partial_text = (context.partial_text or "") .. (data.chunk or "")
        if context.partial_text == "" or is_request_stale(context) then
            return
        end

        vim.schedule(function()
            if not is_request_active(context) or is_request_stale(context) then
                return
            end
            M.show_ghost_text(context.partial_text)
        end)
    end,
})

return M
