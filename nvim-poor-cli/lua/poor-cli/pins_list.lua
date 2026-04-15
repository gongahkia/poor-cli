-- poor-cli/pins_list.lua
-- CB2 follow-up: :PoorCLIPinsList — cross-session viewer/cleaner for
-- turn pin overlay (.poor-cli/turn_pins.json). Lists every pinned turn
-- (soft or hard), with keymaps to unpin individual rows or clear all.

local M = {}

M.buf = nil
M.win = nil
M._rows = {} -- { [line] = { turnId, state } }

local HEADER = {
    "# poor-cli Pinned Turns",
    "",
    "Keys:  x unpin row | X clear all | r refresh | <CR> jump to chat | q close",
    "",
}

local function sort_pins(pins)
    local out = {}
    for turn_id, state in pairs(pins or {}) do
        out[#out + 1] = { turnId = tostring(turn_id), state = tostring(state) }
    end
    table.sort(out, function(a, b)
        if a.state ~= b.state then return a.state < b.state end
        return a.turnId < b.turnId
    end)
    return out
end

M._sort_pins = sort_pins

local function render(pins)
    M._rows = {}
    local lines = {}
    for _, h in ipairs(HEADER) do lines[#lines + 1] = h end
    local items = sort_pins(pins)
    if #items == 0 then
        lines[#lines + 1] = "_no pinned turns_"
    else
        for _, it in ipairs(items) do
            lines[#lines + 1] = string.format("  %-5s  %s", it.state, it.turnId)
            M._rows[#lines] = it
        end
    end
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then return lines end
    vim.bo[M.buf].modifiable = true
    vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, lines)
    vim.bo[M.buf].modifiable = false
    return lines
end

M._render = render

function M.refresh()
    local rpc = require("poor-cli.rpc")
    rpc.request("poor-cli/listTurnPins", {}, function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] listTurnPins: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end
            render((result or {}).pins or {})
        end)
    end)
end

local function row_at_cursor()
    if not (M.win and vim.api.nvim_win_is_valid(M.win)) then return nil end
    return M._rows[vim.api.nvim_win_get_cursor(M.win)[1]]
end

function M.unpin_current()
    local row = row_at_cursor()
    if not row then return end
    local rpc = require("poor-cli.rpc")
    rpc.request("poor-cli/setTurnPin", { turnId = row.turnId, state = vim.NIL }, function(_, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] setTurnPin: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end
            M.refresh()
            -- notify chat buffer to re-hydrate badges
            local ok, tp = pcall(require, "poor-cli.turn_pin")
            if ok then pcall(tp.hydrate) end
        end)
    end)
end

function M.clear_all()
    local rpc = require("poor-cli.rpc")
    rpc.request("poor-cli/listTurnPins", {}, function(result, _err)
        vim.schedule(function()
            local pins = (result or {}).pins or {}
            if vim.tbl_isempty(pins) then
                require("poor-cli.notify").notify("[poor-cli] no pins to clear", vim.log.levels.INFO)
                return
            end
            local choice = vim.fn.confirm(
                string.format("Clear all %d pinned turns?", vim.tbl_count(pins)),
                "&Yes\n&No", 2
            )
            if choice ~= 1 then return end
            local pending = vim.tbl_count(pins)
            for turn_id, _ in pairs(pins) do
                rpc.request("poor-cli/setTurnPin", { turnId = tostring(turn_id), state = vim.NIL }, function()
                    vim.schedule(function()
                        pending = pending - 1
                        if pending <= 0 then
                            M.refresh()
                            local ok, tp = pcall(require, "poor-cli.turn_pin")
                            if ok then pcall(tp.hydrate) end
                            require("poor-cli.notify").notify("[poor-cli] cleared all pins", vim.log.levels.INFO)
                        end
                    end)
                end)
            end
        end)
    end)
end

function M.jump_to_chat()
    local row = row_at_cursor()
    if not row then return end
    local chat = require("poor-cli.chat")
    if not chat.open then return end
    chat.open()
    for _, turn in ipairs(chat.turns or {}) do
        if tostring(turn.id) == row.turnId and chat.win and vim.api.nvim_win_is_valid(chat.win) then
            pcall(vim.api.nvim_win_set_cursor, chat.win, { (turn.start_line or 0) + 1, 0 })
            return
        end
    end
    require("poor-cli.notify").notify("[poor-cli] turn not in current chat buffer", vim.log.levels.WARN)
end

function M.close()
    if M.win and vim.api.nvim_win_is_valid(M.win) then vim.api.nvim_win_close(M.win, true) end
    M.win = nil
end

function M.open()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_set_current_win(M.win)
        M.refresh()
        return
    end
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then
        M.buf = vim.api.nvim_create_buf(false, true)
        vim.bo[M.buf].buftype = "nofile"
        vim.bo[M.buf].bufhidden = "hide"
        vim.bo[M.buf].swapfile = false
        vim.bo[M.buf].filetype = "markdown"
        vim.api.nvim_buf_set_name(M.buf, "[poor-cli pins]")
    end
    vim.cmd("botright 70vsplit")
    M.win = vim.api.nvim_get_current_win()
    vim.api.nvim_win_set_buf(M.win, M.buf)
    vim.wo[M.win].wrap = false
    vim.wo[M.win].number = false
    vim.wo[M.win].relativenumber = false
    vim.keymap.set("n", "q", M.close, { buffer = M.buf, nowait = true, desc = "close" })
    vim.keymap.set("n", "r", M.refresh, { buffer = M.buf, nowait = true, desc = "refresh" })
    vim.keymap.set("n", "x", M.unpin_current, { buffer = M.buf, nowait = true, desc = "unpin" })
    vim.keymap.set("n", "X", M.clear_all, { buffer = M.buf, nowait = true, desc = "clear all" })
    vim.keymap.set("n", "<CR>", M.jump_to_chat, { buffer = M.buf, nowait = true, desc = "jump to chat" })
    M.refresh()
end

function M.toggle()
    if M.win and vim.api.nvim_win_is_valid(M.win) then M.close() else M.open() end
end

function M.setup()
    pcall(vim.api.nvim_del_user_command, "PoorCLIPinsList")
    vim.api.nvim_create_user_command("PoorCLIPinsList", function() M.toggle() end, {
        desc = "poor-cli: view/clear cross-session turn pins",
    })
end

return M
